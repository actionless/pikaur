#!/usr/bin/env bash

# Licensed under GPLv3, see https://www.gnu.org/licenses/

set -euo pipefail
IFS=$'\n\t'

if [[ "${1:-}" = "--help" ]] ; then
	echo "Usage: $0 COVERAGE LINTING TESTS"
	echo "	COVERAGE: ['--local', '--coveralls']"
	echo "	SKIP_LINTING: [0, 1]"
	echo "	TESTSUITE: ['all', <TESTSUITE_NAME_OR_PATH>]"
	exit 1
fi

set -x

cd "$(readlink -e "$(dirname "${0}")")"/.. || exit 2

echo "Github Token:"
if [[ -z "${GITHUB_TOKEN:-}" ]] ; then
	echo " NOT FOUND"
else
	echo " FOUND"
fi

return_code=0
sudo docker build ./ \
	--build-arg GITHUB_TOKEN="${GITHUB_TOKEN:-}" \
	--build-arg GITHUB_RUN_ID="${GITHUB_RUN_ID:-}" \
	--build-arg GITHUB_REF="${GITHUB_REF:-}" \
	--build-arg MODE="${1:---local}" \
	--build-arg SKIP_LINTING="${2:-0}" \
	--build-arg TESTSUITE="${3:-all}" \
	-t pikaur -f ./Dockerfile \
	|| return_code=$?

echo "Exited with $return_code"
exit ${return_code}
