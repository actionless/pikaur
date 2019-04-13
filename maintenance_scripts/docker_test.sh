#!/usr/bin/env bash

# This file is licensed under GPLv3, see https://www.gnu.org/licenses/

set -euo pipefail
IFS=$'\n\t'

set -x

cd "$(readlink -e "$(dirname "${0}")")"/.. || exit 2


rm -fr ./htmlcov/*
mkdir -p ./htmlcov/


sudo docker build ./ -t pikaur -f ./Dockerfile

return_code=0
sudo docker \
	container run \
	--dns="8.8.8.8" \
	--tty \
	--interactive \
	--volume /run/dbus/system_bus_socket:/run/dbus/system_bus_socket:ro \
	--volume "$(readlink -e ./htmlcov/)":/opt/app-build/htmlcov \
	pikaur:latest \
	sudo \
		-u user \
		env TRAVIS="${TRAVIS:-}" \
			TRAVIS_JOB_ID="${TRAVIS_JOB_ID:-}" \
			TRAVIS_BRANCH="${TRAVIS_BRANCH:-}" \
			TRAVIS_PULL_REQUEST="${TRAVIS_PULL_REQUEST:-}" \
		./maintenance_scripts/ci.sh "${1:--local}" --write-db \
	|| return_code=$?

if [[ "${1:-}" == "--local" ]] && [[ ${return_code} -eq 0 ]] ; then
	firefox htmlcov/index.html
fi

echo "Exited with $return_code"
exit ${return_code}
