#!/usr/bin/env bash
set -euo pipefail

pylint pikaur.py pikaur
mypy --ignore-missing-imports pikaur
flake8
