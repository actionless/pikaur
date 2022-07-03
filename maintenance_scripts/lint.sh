#!/usr/bin/env bash
set -euo pipefail

script_dir=$(readlink -e "$(dirname "${0}")")
APP_DIR="$(readlink -e "${script_dir}"/..)"

TARGETS=(
	'pikaur'
	'pikaur_test'
)

export PYTHONWARNINGS='default,error:::pikaur[.*],error:::pikaur_test[.*]'

echo Python compile...
python3 -O -m compileall "${TARGETS[@]}" | (grep -v -e '^Listing' -e '^Compiling' || true)

echo Flake8...
flake8 "${TARGETS[@]}" 2>&1 \
| (
	grep -v \
		-e "^  warnings.warn($" \
		-e "^/usr/lib/python3.10/site-packages/" \
	|| true \
)

echo PyLint...
#python -m pylint --jobs="$(nproc)" "${TARGETS[@]}" --score no 2>&1 \
# @TODO: --jobs is broken at the moment: https://github.com/PyCQA/pylint/issues/374
python -m pylint "${TARGETS[@]}" --score no 2>&1 \
| (
	grep -v \
		-e "^  warnings.warn($" \
		-e "^/usr/lib/python3.10/site-packages/" \
	|| true \
)

echo MyPy...
python -m mypy "${TARGETS[@]}"

echo Vulture...
	#--exclude argparse.py \
vulture "${TARGETS[@]}" \
	./maintenance_scripts/vulture_whitelist.py \
	--min-confidence=1 \
	--sort-by-size

echo Bandit...
bandit . --recursive --silent

echo Shellcheck...
(
	cd "${APP_DIR}"
	# shellcheck disable=SC2046
	shellcheck $(find . \
		-name '*.sh' \
	)
)

echo '== GOOD!'
