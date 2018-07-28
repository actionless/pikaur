#!/usr/bin/env bash
# shellcheck disable=SC2016

# This file is licensed under GPLv3, see https://www.gnu.org/licenses/

set -euo pipefail
IFS=$'\n\t'
aur_repo_dir=~/build/pikaur
aur_dev_repo_dir=~/build/pikaur-git
src_repo_dir=$(readlink -e $(dirname "${0}"))

new_version=$1

if [[ $(git status --porcelain 2>/dev/null| grep -c "^ [MD]") -gt 0 ]] ; then
	echo
	echo "   !!! You have uncommited changes: !!!"
	echo
	git status
	exit 1
fi

sed -i -e "s/pkgver=.*/pkgver=${new_version}/g" PKGBUILD
sed -i -e "s/pkgrel=.*/pkgrel=1/g" PKGBUILD
sed -i -e "s/VERSION.*=.*/VERSION = '${new_version}-dev'/g" pikaur/config.py
sed -i -e "s/    version='.*',/    version='${new_version}',/g" setup.py
git commit -am "chore: bump version to ${new_version}" || true
git tag -a "${new_version}" -f

echo "[confirm push to pikaur git repo?]"
read -r
git push origin HEAD
git push origin "${new_version}"


git tag -n9 > "${aur_dev_repo_dir}"/CHANGELOG
cp PKGBUILD "${aur_dev_repo_dir}"/PKGBUILD
# shellcheck disable=SC2164
cd "${aur_dev_repo_dir}"
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO CHANGELOG
git commit -m "update to ${new_version}"

echo "[confirm push to AUR dev package?]"
read -r
git push origin HEAD


cd "${src_repo_dir}"
git tag -n9 > "${aur_repo_dir}"/CHANGELOG
sed \
	-e 's|pkgname=pikaur-git|pkgname=pikaur|' \
	-e 's|"$pkgname::git+https://github.com/actionless/pikaur.git#branch=master"|"$pkgname-$pkgver.tar.gz"::https://github.com/actionless/pikaur/archive/"$pkgver".tar.gz|' \
	-e "s|conflicts=('pikaur')|conflicts=('pikaur-git')|" \
	-e 's|cd "${srcdir}/${pkgname}"|cd "${srcdir}/${pkgname}-${pkgver}"|' \
	-e '/pkgver() {/,+5 d' \
	PKGBUILD > "${aur_repo_dir}"/PKGBUILD
# shellcheck disable=SC2164
cd "${aur_repo_dir}"
updpkgsums
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO CHANGELOG
git commit -m "update to ${new_version}"

echo "[confirm push to AUR stable package?]"
read -r
git push origin HEAD
