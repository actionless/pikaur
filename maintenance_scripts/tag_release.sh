#!/usr/bin/env bash
# shellcheck disable=SC2016

# Licensed under GPLv3, see https://www.gnu.org/licenses/

set -euo pipefail
IFS=$'\n\t'

aur_repo_dir=~/build/pikaur
aur_dev_repo_dir=~/build/pikaur-git
aur_static_repo_dir=~/build/pikaur-static
aur_static_dev_repo_dir=~/build/pikaur-static-git

src_repo_dir=$(readlink -e "$(dirname "${0}")"/..)
src_pkgbuild="${src_repo_dir}/PKGBUILD"
src_pkgbuild_static="${src_repo_dir}/pikaur_static/PKGBUILD"

new_version=$1


for repo_dir in "$aur_repo_dir" "$aur_dev_repo_dir" "$aur_static_repo_dir" "$aur_static_dev_repo_dir" ; do
	if [[ ! -d "$repo_dir" ]] ; then
		echo
		echo " !! Repository $repo_dir/ does not exists"
		echo
		exit 1
	fi
done


if [[ $(git status --porcelain 2>/dev/null| grep -c "^ [MD]" || true) -gt 0 ]] ; then
	echo
	echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
	echo "!!    You have uncommitted changes:    !!"
	echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
	echo
	git status

	echo
	echo "?????????????????????????????????????????"
	echo "??    Do you want to proceed? [y/N]    ??"
	echo "?????????????????????????????????????????"
	echo -n "> "
	read -r answer
	echo
	if [[ "${answer}" != "y" ]] ; then
		exit 1
	fi
	answer=
fi

cd "${src_repo_dir}"
./maintenance_scripts/show_recent_history.sh -c || true

###############################################################################

echo
echo "*******************************"
echo "**    Updating version...    **"
echo "*******************************"
echo

for pkgbuild in "$src_pkgbuild" "$src_pkgbuild_static" ; do
	sed -i -e "s/^pkgver=.*/pkgver=${new_version}/g" "$pkgbuild"
	sed -i -e "s/^pkgrel=.*/pkgrel=1/g" "$pkgbuild"
done
sed -i -e "s/^VERSION: .*=.*/VERSION: \"Final\" = \"${new_version}-dev\"/g" pikaur/config.py
sed -i -e "s/^version = '.*'/version = '${new_version}'/g" pyproject.toml

echo
echo "??????????????????????????????????????????????????????????????????????"
echo "??    Confirm pushing ${new_version} to Pikaur GitHub repo? [y/N]   ??"
echo "??????????????????????????????????????????????????????????????????????"
echo -n "> "
read -r answer
echo
if [[ "${answer}" = "y" ]] ; then
	git add "$src_pkgbuild" "$src_pkgbuild_static" pyproject.toml pikaur/config.py
	git commit -m "chore: bump version to ${new_version}" || true
	git tag -a "${new_version}"
	git push origin HEAD
	git push origin "${new_version}"
fi
answer=

###############################################################################

echo
echo "***************************************"
echo "**    Updating AUR dev PKGBUILD...   **"
echo "***************************************"
echo
cd "${src_repo_dir}"
./maintenance_scripts/changelog.sh > "${aur_dev_repo_dir}"/CHANGELOG
cp "$src_pkgbuild" "${aur_dev_repo_dir}"/PKGBUILD
# shellcheck disable=SC2164
cd "${aur_dev_repo_dir}"
makepkg --printsrcinfo > .SRCINFO
echo
echo "??????????????????????????????????????????????????"
echo "??    Confirm push to AUR dev package? [y/N]    ??"
echo "??????????????????????????????????????????????????"
echo -n "> "
read -r answer
echo
if [[ "${answer}" = "y" ]] ; then
	git add PKGBUILD .SRCINFO CHANGELOG
	git commit -m "update to ${new_version}"
	GIT_SSH_COMMAND="ssh -i ~/.ssh/aur" git push origin HEAD
fi
answer=


echo
echo "*******************************************"
echo "**    Updating AUR release PKGBUILD...   **"
echo "*******************************************"
echo
cd "${src_repo_dir}"
./maintenance_scripts/changelog.sh > "${aur_repo_dir}"/CHANGELOG
sed \
	-e 's|pkgname="${_pkgname}-git"|pkgname="${_pkgname}"|' \
	-e 's|"$pkgname::git+${url}.git#branch=master"|"$pkgname-$pkgver.tar.gz"::${url}/archive/"$pkgver".tar.gz|' \
	-e 's|conflicts=("$_pkgname")|conflicts=("${_pkgname}-git")|' \
	-e 's|cd "${srcdir}/${pkgname}"|cd "${srcdir}/${pkgname}-${pkgver}"|' \
	-e '/pkgver() {/,+5 d' \
	"$src_pkgbuild" > "${aur_repo_dir}"/PKGBUILD
# shellcheck disable=SC2164
cd "${aur_repo_dir}"
updpkgsums
makepkg --printsrcinfo > .SRCINFO
echo
echo "??????????????????????????????????????????????????????"
echo "??    Confirm push to AUR release package? [y/N]    ??"
echo "??????????????????????????????????????????????????????"
echo -n "> "
read -r answer
echo
if [[ "${answer}" = "y" ]] ; then
	git add PKGBUILD .SRCINFO CHANGELOG
	git commit -m "update to ${new_version}"
	GIT_SSH_COMMAND="ssh -i ~/.ssh/aur" git push origin HEAD
fi
answer=

###############################################################################

echo
echo "**********************************************"
echo "**    Updating AUR static dev PKGBUILD...   **"
echo "**********************************************"
echo
cd "${src_repo_dir}"
./maintenance_scripts/changelog.sh > "${aur_static_dev_repo_dir}"/CHANGELOG
cp "$src_pkgbuild_static" "${aur_static_dev_repo_dir}"/PKGBUILD
# shellcheck disable=SC2164
cd "${aur_static_dev_repo_dir}"
makepkg --printsrcinfo > .SRCINFO
echo
echo "?????????????????????????????????????????????????????????"
echo "??    Confirm push to AUR static dev package? [y/N]    ??"
echo "?????????????????????????????????????????????????????????"
echo -n "> "
read -r answer
echo
if [[ "${answer}" = "y" ]] ; then
	git add PKGBUILD .SRCINFO CHANGELOG
	git commit -m "update to ${new_version}"
	GIT_SSH_COMMAND="ssh -i ~/.ssh/aur" git push origin HEAD
fi
answer=


echo
echo "**************************************************"
echo "**    Updating AUR static release PKGBUILD...   **"
echo "**************************************************"
echo
cd "${src_repo_dir}"
./maintenance_scripts/changelog.sh > "${aur_static_repo_dir}"/CHANGELOG
sed \
	-e 's|pkgname="${_pkgname}-git"|pkgname="${_pkgname}"|' \
	-e 's|"$pkgname::git+${url}.git#branch=master"|"$pkgname-$pkgver.tar.gz"::${url}/archive/"$pkgver".tar.gz|' \
	-e 's|conflicts=("$_pkgname")|conflicts=("${_pkgname}-git")|' \
	-e 's|${srcdir}/${pkgname}|${srcdir}/pikaur-${pkgver}|' \
	-e '/pkgver() {/,+5 d' \
	"$src_pkgbuild_static" > "${aur_static_repo_dir}"/PKGBUILD
# shellcheck disable=SC2164
cd "${aur_static_repo_dir}"
updpkgsums
makepkg --printsrcinfo > .SRCINFO
echo
echo "?????????????????????????????????????????????????????????????"
echo "??    Confirm push to AUR static release package? [y/N]    ??"
echo "?????????????????????????????????????????????????????????????"
echo -n "> "
read -r answer
echo
if [[ "${answer}" = "y" ]] ; then
	git add PKGBUILD .SRCINFO CHANGELOG
	git commit -m "update to ${new_version}"
	GIT_SSH_COMMAND="ssh -i ~/.ssh/aur" git push origin HEAD
fi
answer=

###############################################################################

echo
echo "??????????????????????????????????????????????????????"
echo "??    Confirm push to PyPI release package? [y/N]   ??"
echo "??????????????????????????????????????????????????????"
echo -n "> "
read -r answer
echo
if [[ "${answer}" = "y" ]] ; then
	cd "${src_repo_dir}"
	rm -fr ./dist
	python -m build --wheel --no-isolation
	twine check ./dist/*.whl
	twine upload ./dist/*.whl
fi
answer=

###############################################################################

echo
echo '$$$$$$$$$$$$$$$$$$$$$$$$$'
echo '$$    Full Success!    $$'
echo '$$$$$$$$$$$$$$$$$$$$$$$$$'

exit 0
