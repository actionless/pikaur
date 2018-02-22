#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

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
