#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'


export PATH="${PATH}:/usr/bin/core_perl"
echo "PKGEXT='.pkg.tar'" >> ~/.makepkg.conf

if [[ "${2:-}" == "--write-db" ]] ; then
	export WRITE_DB=True
fi
coverage run --source=pikaur -m unittest -v

if [[ "${1:-}" == "--coveralls" ]] ; then
	coveralls --service=github
else
	coverage report
	coverage html
fi
