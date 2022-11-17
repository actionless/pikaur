#!/bin/bash

# Licensed under GPLv3, see https://www.gnu.org/licenses/

REPO_ROOT="$(readlink -e "$(dirname "${0}")")"/..
exec docker \
	container run \
	--tty \
	--interactive \
	--rm \
	--volume "${REPO_ROOT}":/opt/app-build \
	"$@" \
	pikaur:latest
