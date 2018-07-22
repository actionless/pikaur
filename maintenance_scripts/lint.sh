#!/usr/bin/env bash
set -euo pipefail

flake8 pikaur pikaur.py pikaur_test
pylint pikaur.py pikaur pikaur_test
mypy --ignore-missing-imports pikaur.py pikaur_test
./maintenance_scripts/vulture.sh
