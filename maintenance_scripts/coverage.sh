#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'


virtualenv --system-site-packages coverage_env
set +u
source coverage_env/bin/activate
set -u

pip install coveralls

gpg --recv-keys 1EB2638FF56C0C53  # Dave Reisner, cower
export PATH="${PATH}:/usr/bin/core_perl"

coverage run --source=pikaur run_tests.py ${2:-}

if [[ "${1:-}" == "--coveralls" ]] ; then
	coveralls
else
	coverage report
	coverage html
fi

deactivate
