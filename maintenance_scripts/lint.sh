#!/usr/bin/env bash
set -euo pipefail

script_dir=$(readlink -e "$(dirname "${0}")")
APP_DIR="$(readlink -e "${script_dir}"/..)"


FIX_MODE=0
while getopts f name
do
	case $name in
	f)	FIX_MODE=1;;
	?)	printf "Usage: %s: [-f] [TARGETS]\n" "$0"
		echo "Arguments:"
		echo "	-f	run in fix mode"
		exit 2;;
	esac
done
shift $((OPTIND - 1))
if [[ -n "$*" ]] ; then
	printf "\nRemaining arguments are: %s\n$*\n\n"
fi


PYTHON=python3

TARGETS=(
	'pikaur'
	'pikaur_test'
	./maintenance_scripts/*.py
	packaging/usr/bin/pikaur
)
if [[ -n "${1:-}" ]] ; then
	TARGETS=("$@")
fi


install_ruff() {
	if [[ ! -f "${APP_DIR}/env/bin/activate" ]] ; then
		"$PYTHON" -m venv "${APP_DIR}/env" --system-site-packages
		# shellcheck disable=SC1091
		. "${APP_DIR}/env/bin/activate"
		"$PYTHON" -m pip install ruff --upgrade
		deactivate
	fi
}
RUFF="${APP_DIR}/env/bin/ruff"


if [[ "$FIX_MODE" -eq 1 ]] ; then
	"$RUFF" check --unsafe-fixes --fix "${TARGETS[@]}"
else
	export PYTHONWARNINGS='ignore,error:::pikaur[.*],error:::pikaur_test[.*]'


	echo Python compile...
	"$PYTHON" -O -m compileall "${TARGETS[@]}" \
	| (\
		grep -v -e '^Listing' -e '^Compiling' || true \
	)

	echo Python import...
	#"$PYTHON" -c "import pikaur"
	"$PYTHON" -c "import pikaur.main"

	echo Checking for non-Final globals...
	./maintenance_scripts/get_non_final_expressions.sh

	echo Checking for unreasonable global vars...
	./maintenance_scripts/get_global_expressions.sh

	install_ruff
	echo Ruff rules up-to-date...
	diff --color -u \
		<(awk '/select = \[/,/]/' pyproject.toml \
			| sed -e 's|", "|/|g' \
			| head -n -1 \
			| tail -n +2 \
			| tr -d '",#' \
			| awk '{print $1;}' \
			| sort) \
		<("$RUFF" linter \
			| awk '{print $1;}' \
			| sort)
	echo Ruff...
	"$RUFF" check "${TARGETS[@]}"

	echo Flake8...
	"$PYTHON" -m flake8 "${TARGETS[@]}"

	echo PyLint...
	"$PYTHON" -m pylint "${TARGETS[@]}" --score no

	echo MyPy...
	"$PYTHON" -m mypy "${TARGETS[@]}" --no-error-summary

	echo Vulture...
		#--exclude argparse.py \
	"$PYTHON" -m vulture "${TARGETS[@]}" \
		./maintenance_scripts/vulture_whitelist.py \
		--min-confidence=1 \
		--sort-by-size

	echo Bandit...
	# if `grep -R nosec pikaur | grep -v noqa` would start returning nothing - bandit check might be removed safely
	"$PYTHON" -m bandit "${TARGETS[@]}" --recursive --silent

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
		"$PYTHON" ./maintenance_scripts/makefile_shellcheck.py
	)

	echo Validate pyproject file...
	(
		exit_code=0
		result=$(validate-pyproject pyproject.toml 2>&1) || exit_code=$?
		if [[ $exit_code -gt 0 ]] ; then
			echo "$result"
			exit $exit_code
		fi
	)

fi

echo '== GOOD!'
