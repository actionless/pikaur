#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'


vulture pikaur/ --exclude argparse.py --sort-by-size --min-confidence=1
