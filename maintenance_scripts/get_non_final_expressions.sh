#!/bin/bash
set -ue

result=$(
	grep -REn "^[a-zA-Z_]+ = " pikaur --color=always \
	| grep -Ev \
		-e ': Final' \
		-e '\|' \
		\
		-e '(dict|list|str)\[' \
		-e TypeVar \
		-e namedtuple \
		\
		-e 'create_debug_logger' \
	| sort
)
result_lines="$(wc -l <<< "$result")"
echo -n "$result"
exit "$(test "$result_lines" -eq 0 -o "$result" = "" && echo 0 || echo 1)"
