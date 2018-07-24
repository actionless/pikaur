#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'


	#--exclude argparse.py \
exec vulture pikaur/ pikaur_test/ \
	--min-confidence=1 \
	--sort-by-size \
	./maintenance_scripts/vulture_whitelist.py
