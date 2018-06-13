#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'


exec vulture pikaur/ \
	--min-confidence=1 \
	--sort-by-size \
	--exclude argparse.py \
	./maintenance_scripts/vulture_whitelist.py
