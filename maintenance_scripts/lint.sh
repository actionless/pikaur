#!/usr/bin/env bash
set -euo pipefail

script_dir=$(readlink -e "$(dirname "${0}")")
APP_DIR="$(readlink -e "${script_dir}"/..)"

TARGETS=(
	'pikaur'
	'pikaur_test'
)

echo Python compile...
python3 -O -m compileall "${TARGETS[@]}" | (grep -v -e '^Listing' -e '^Compiling' || true)

echo Flake8...
flake8 "${TARGETS[@]}"

echo PyLint...
python -m pylint --jobs="$(nproc)" "${TARGETS[@]}" --score no

echo MyPy...
env MYPYPATH=./maintenance_scripts/mypy_stubs python -m mypy "${TARGETS[@]}"

echo Vulture...
	#--exclude argparse.py \
vulture "${TARGETS[@]}" \
	./maintenance_scripts/vulture_whitelist.py \
	--min-confidence=1 \
	--sort-by-size

echo Shellcheck...
(
	cd "${APP_DIR}"
	# shellcheck disable=SC2046
	shellcheck $(find . \
		-name '*.sh' \
	)
)

echo '== GOOD!'
