#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

cd $(readlink -e $(dirname "${0}"))/..


./maintenance_scripts/lint.sh
./maintenance_scripts/coverage.sh ${1:---local} ${2:---write-db}
