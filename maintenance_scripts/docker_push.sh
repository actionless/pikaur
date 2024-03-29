#!/bin/sh
set -ue

tag=${1:-$(date "+%Y%m%d")}

docker build . --pull -t actionless/pikaur:"$tag" -f Dockerfile_export --ulimit nofile=1024:524288
docker tag actionless/pikaur:"$tag" actionless/pikaur:latest
docker push actionless/pikaur:latest
