#!/usr/bin/env bash

# Licensed under GPLv3, see https://www.gnu.org/licenses/

set -euo pipefail
IFS=$'\n\t'

if [[ "${1:-}" = "--help" ]] ; then
	echo "Usage: $0 COVERAGE SKIP_LINTING TESTSUITE [TESTSUITE_2 ... TESTSUITE_N]"
	echo "	COVERAGE: ['--local', '--coveralls']"
	echo "	SKIP_LINTING: [0, 1]"
	echo "	TESTSUITE: ['all', <TESTSUITE_NAME_OR_PATH>]"
	# shellcheck disable=SC2016
	echo '
and TESTSUITE could be specified in a same way as in `unittest`:

```
test_module               - run tests from test_module
module.TestClass          - run tests from module.TestClass
module.Class.test_method  - run specified test method
path/to/test_file.py      - run tests from test_file.py
```'
	exit 1
fi

set -x

OUTPUT_DIR="${OUTPUT_DIR:-.}"

MODE="${1:---local}"
shift
SKIP_LINTING="${1:-0}"
shift
# shellcheck disable=SC2124
TESTSUITE="${@:-all}"
shift

cd "$(readlink -e "$(dirname "${0}")")"/.. || exit 2

echo "Github Token:"
if [[ -z "${GITHUB_TOKEN:-}" ]] ; then
	echo " NOT FOUND"
else
	echo " FOUND"
fi

DOCKER_TAG=pikaur
if [[ "$MODE" == "--worker" ]] ; then
	worker_id="$(cut -d, -f1 <<< "$TESTSUITE")"
	DOCKER_TAG="pikaur_${worker_id}"
fi

return_code=0
sudo docker build ./ \
	--ulimit nofile=1024:524288 \
	--progress plain \
	--build-arg GITHUB_TOKEN="${GITHUB_TOKEN:-}" \
	--build-arg GITHUB_RUN_ID="${GITHUB_RUN_ID:-}" \
	--build-arg GITHUB_REF="${GITHUB_REF:-}" \
	--build-arg MODE="$MODE" \
	--build-arg SKIP_LINTING="$SKIP_LINTING" \
	--build-arg TESTSUITE="$TESTSUITE" \
	-t "$DOCKER_TAG" \
	-f ./Dockerfile \
	|| return_code=$?

echo "Exited with $return_code"

if [[ "$MODE" == "--worker" ]] ; then
	id=$(docker create "$DOCKER_TAG")
	docker cp "$id":/opt/app-build/.coverage "${OUTPUT_DIR}/coverage_${worker_id}"
	docker cp "$id":/opt/app-build/pikaur_test_times.txt "${OUTPUT_DIR}/pikaur_test_times_${worker_id}"
	docker rm -v "$id"
fi

exit ${return_code}
