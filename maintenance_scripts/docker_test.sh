#!/usr/bin/env bash

# This file is licensed under GPLv3, see https://www.gnu.org/licenses/

#set -euo pipefail
IFS=$'\n\t'

cd $(readlink -e $(dirname "${0}"))/..

rm -fr ./htmlcov/*
mkdir -p ./htmlcov/


sudo docker build ./ -t pikaur -f ./Dockerfile

sudo docker \
	container run \
	--tty \
	--interactive \
	--volume /run/dbus/system_bus_socket:/run/dbus/system_bus_socket:ro \
	--detach \
	--volume $(readlink -e ./htmlcov/):/opt/app-build/htmlcov \
	pikaur:latest

container_name=$(sudo docker container ls --quiet --filter ancestor=pikaur:latest)
sudo docker \
	container exec \
	--tty \
	--interactive \
	${container_name} \
	sudo \
		-u user \
		env TRAVIS="$TRAVIS" \
			TRAVIS_JOB_ID="$TRAVIS_JOB_ID" \
			TRAVIS_BRANCH="$TRAVIS_BRANCH" \
			TRAVIS_PULL_REQUEST="$TRAVIS_PULL_REQUEST" \
		./maintenance_scripts/ci.sh ${1:--local} --write-db
return_code=$?

sudo docker \
	container kill \
	${container_name} > /dev/null

if [[ "${1:-}" == "--local" ]] && [[ ${return_code} -eq 0 ]] ; then
	firefox htmlcov/index.html
fi

echo "Exited with $return_code"
exit ${return_code}
