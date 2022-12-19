#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

MODE="${1:---local}"
shift
if [[ "$MODE" == "--help" ]] ; then
	echo "Usage: $0 SUBMIT_COVERAGE WRITE_DB"
	exit 0
fi

IS_WRITE_DB="${1:---write-db}"
shift
if [[ "$IS_WRITE_DB" == "--write-db" ]] ; then
	export WRITE_DB=True
	export PATH="${PATH}:/usr/bin/core_perl"
	echo "PKGEXT='.pkg.tar'" >> ~/.makepkg.conf
fi

#ping 8.8.8.8 -c 1 || {
#    echo "No internet connection"
#    exit 1
#}

coverage run --source=pikaur -m unittest -v "$@"

if [[ "$MODE" == "--coveralls" ]] ; then
	coveralls --service=github
else
	coverage report
	coverage html
fi
