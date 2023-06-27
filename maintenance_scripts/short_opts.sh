#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

filter() {
	cat | grep -e "-.," -o | tr -d ',' | tr -d '%' | sort || true
}

get_pacman() {
	echo "pacman -$1"
	(pacman -"$1"h 2>&1 || true) | filter
}

get_pikaur() {
	echo "pikaur -$1"
	./pikaur.py -"$1"h | sed -n -e '/Pikaur-specific/,$p' | filter
}

print_columns() {
	paste "$@" | sed -e 's/\t/\t\t/g' -e 's/\t\(pacman\|pikaur\)/\1/g'
}

print_columns <(get_pacman S) <(get_pacman Q) <(get_pacman U) <(get_pacman R) <(get_pacman T) <(get_pacman F) <(get_pacman D) <(get_pacman P) <(get_pacman G)
echo
print_columns <(get_pikaur S) <(get_pikaur Q) <(get_pikaur U) <(get_pikaur R) <(get_pikaur T) <(get_pikaur F) <(get_pikaur D) <(get_pikaur P) <(get_pikaur G)
