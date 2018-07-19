#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'


virtualenv --system-site-packages coverage_env
set +u
source coverage_env/bin/activate
set -u

pip install coveralls

export PATH="${PATH}:/usr/bin/core_perl"
echo "PKGEXT='.pkg.tar'" >> ~/.makepkg.conf

coverage run --source=pikaur -m unittest ${2:-}

if [[ "${1:-}" == "--coveralls" ]] ; then
	coveralls
else
	coverage report
	coverage html
fi

deactivate
