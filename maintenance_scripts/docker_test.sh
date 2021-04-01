#!/usr/bin/env bash

# This file is licensed under GPLv3, see https://www.gnu.org/licenses/

set -euo pipefail
IFS=$'\n\t'

set -x

cd "$(readlink -e "$(dirname "${0}")")"/.. || exit 2


return_code=0
sudo docker build ./ \
	--build-arg GITHUB_TOKEN="${GITHUB_TOKEN:-}" \
	--build-arg MODE="${1:---local}" \
	-t pikaur -f ./Dockerfile \
	|| return_code=$?

echo "Exited with $return_code"
exit ${return_code}
