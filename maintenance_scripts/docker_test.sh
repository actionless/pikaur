#!/usr/bin/env bash

# This file is licensed under GPLv3, see https://www.gnu.org/licenses/

set -euo pipefail
IFS=$'\n\t'

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
	-t pikaur -f ./Dockerfile \
	|| return_code=$?

echo "Exited with $return_code"
exit ${return_code}
