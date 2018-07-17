#!/usr/bin/env bash
set -euo pipefail

flake8 pikaur pikaur.py pikaur_test run_tests.py
pylint pikaur.py pikaur pikaur_test run_tests.py
mypy --ignore-missing-imports pikaur.py pikaur_test
