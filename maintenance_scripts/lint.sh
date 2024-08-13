#!/usr/bin/env bash
set -ueo pipefail

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
RUFF=ruff
TARGET_MODULE='pikaur'
TARGETS=(
	'./pikaur/'
	'./pikaur_test/'
	'./pikaur_meta_helpers/'
	./maintenance_scripts/*.py
	'./packaging/usr/bin/pikaur'
)
if [[ -n "${1:-}" ]] ; then
	TARGETS=("$@")
fi




if [[ "$FIX_MODE" -eq 1 ]] ; then
	"$RUFF" check --fix "${TARGETS[@]}"
else
	export PYTHONWARNINGS='ignore,error:::'"$TARGET_MODULE"'[.*],error:::pikaur_test[.*]'

	echo -e "\n== Running python compile:"
	"$PYTHON" -O -m compileall "${TARGETS[@]}" \
	| (\
		grep -v -e '^Listing' -e '^Compiling' || true \
	)
	echo ':: python compile passed ::'

	echo -e "\n== Running python import:"
	"$PYTHON" -c "import ${TARGET_MODULE}.main"
	echo ':: python import passed ::'

	echo -e "\n== Checking for non-Final globals:"
	./maintenance_scripts/get_non_final_expressions.sh "${TARGETS[@]}"
	echo ':: check passed ::'

	echo -e "\n== Checking for unreasonable global vars:"
	./maintenance_scripts/get_global_expressions.sh "${TARGETS[@]}"
	echo ':: check passed ::'

	echo -e "\n== Checking Ruff rules up-to-date:"
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
	echo -e "\n== Ruff..."
	"$RUFF" check "${TARGETS[@]}"
	echo ':: ruff passed ::'

	echo -e "\n== Running flake8:"
	"$PYTHON" -m flake8 "${TARGETS[@]}"
	echo ':: flake8 passed ::'

	echo -e "\n== Running pylint:"
	"$PYTHON" -m pylint "${TARGETS[@]}" --score no
	echo ':: pylint passed ::'

	echo -e "\n== Running mypy:"
	"$PYTHON" -m mypy "${TARGETS[@]}" --no-error-summary
	echo ':: mypy passed ::'

	echo -e "\n== Running vulture:"
		#--exclude argparse.py \
	"$PYTHON" -m vulture "${TARGETS[@]}" \
		./maintenance_scripts/vulture_whitelist.py \
		--min-confidence=1 \
		--sort-by-size
	echo ':: vulture passed ::'

	echo Bandit...
	# if `grep -R nosec pikaur | grep -v noqa` would start returning nothing - bandit check might be removed safely
	"$PYTHON" -m bandit "${TARGETS[@]}" --recursive --silent

	echo -e "\n== Running shellcheck:"
	(
		cd "${APP_DIR}"
		# shellcheck disable=SC2046
		shellcheck $(find . \
			-name '*.sh' \
		)
	)
	echo ':: shellcheck passed ::'
	echo -e "\n== Running shellcheck on Makefile..."
	(
		cd "${APP_DIR}"
		"$PYTHON" ./maintenance_scripts/makefile_shellcheck.py
	)
	echo ':: shellcheck makefile passed ::'

	echo -e "\n== Validate pyproject file..."
	(
		exit_code=0
		result=$(validate-pyproject pyproject.toml 2>&1) || exit_code=$?
		if [[ $exit_code -gt 0 ]] ; then
			echo "$result"
			exit $exit_code
		fi
	)
	echo ':: pyproject validation passed ::'

fi

echo -e '\n== GOOD!'
