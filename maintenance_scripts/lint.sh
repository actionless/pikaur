#!/usr/bin/env bash
set -euo pipefail

echo Flake8:
flake8 pikaur pikaur.py pikaur_test

echo PyLint:
pylint pikaur.py pikaur pikaur_test

echo MyPy:
env MYPYPATH=./maintenance_scripts/mypy_stubs:/usr/lib/python3.7/site-packages/ mypy pikaur.py pikaur_test

echo Vulture:
./maintenance_scripts/vulture.sh

echo == GOOD!
