#!/usr/bin/env bash
set -euo pipefail

script_dir=$(readlink -e "$(dirname "${0}")")
APP_DIR="$(readlink -e "${script_dir}"/..)"

TARGETS=(
	'pikaur'
	'pikaur_test'
	./maintenance_scripts/*.py
)
if [[ -n "${1:-}" ]] ; then
	TARGETS=("$1")
fi

export PYTHONWARNINGS='default,error:::pikaur[.*],error:::pikaur_test[.*]'

echo Python compile...
python3 -O -m compileall "${TARGETS[@]}" \
| (\
	grep -v -e '^Listing' -e '^Compiling' || true \
)

echo Python import...
#python3 -c "import pikaur"
python3 -c "import pikaur.main"

echo Checking for non-Final globals...
./maintenance_scripts/get_non_final_expressions.sh

echo Checking for unreasonable global vars...
./maintenance_scripts/get_global_expressions.sh

echo Ruff...
if [[ ! -f "${APP_DIR}/env/bin/activate" ]] ; then
	python -m venv "${APP_DIR}/env" --system-site-packages
	# shellcheck disable=SC1091
	. "${APP_DIR}/env/bin/activate"
	pip install ruff --upgrade
	deactivate
fi
"${APP_DIR}/env/bin/ruff" "${TARGETS[@]}"

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
bandit "${TARGETS[@]}" --recursive --silent

echo Shellcheck...
(
	cd "${APP_DIR}"
	# shellcheck disable=SC2046
	shellcheck $(find . \
		-name '*.sh' \
	)
)
echo Shellcheck Makefile...
(
	cd "${APP_DIR}"
	./maintenance_scripts/makefile_shellcheck.py
)

echo '== GOOD!'
