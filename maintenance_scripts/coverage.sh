#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
set -x

MODE="${1:---local}"
shift
if [[ "$MODE" == "--help" ]] ; then
	echo "Usage: $0 [SUBMIT_COVERAGE=--local] [WRITE_DB=--write-db] [TESTSUITE=all]"
	exit 0
fi

IS_WRITE_DB="${1:---write-db}"
shift
if [[ "$IS_WRITE_DB" == "--write-db" ]] ; then
	export WRITE_DB=True
	export PATH="${PATH}:/usr/bin/core_perl"
	echo "PKGEXT='.pkg.tar'" >> ~/.makepkg.conf
fi

if [[ "$MODE" == "--worker" ]] ; then
	WORKER_PARAMS="$1"
	# shellcheck disable=SC2207
	TESTSUITE=($(python ./maintenance_scripts/discover_tests_per_worker.py "$(cut -d, -f1 <<< "$WORKER_PARAMS")" "$(cut -d, -f2 <<< "$WORKER_PARAMS")"))
else
	# shellcheck disable=SC2178
	TESTSUITE="${1:-all}"
fi
shift

#ping 8.8.8.8 -c 1 || {
#    echo "No internet connection"
#    exit 1
#}

if [[ -n "${TESTSUITE-}" ]] ; then
	echo > pikaur_test_times.txt
	# shellcheck disable=SC2128
	if [[ "$TESTSUITE" = "all" ]] ; then
		coverage run --source=pikaur -m unittest -v --durations 50 "$@"
	else
		coverage run --source=pikaur -m unittest -v --durations 50 "${TESTSUITE[@]}" "$@"
	fi

	if [[ "$MODE" == "--coveralls" ]] ; then
		coveralls --service=github
	else
		coverage report
		coverage html
	fi
fi
