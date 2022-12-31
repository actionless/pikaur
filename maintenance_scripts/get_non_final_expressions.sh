#!/bin/bash
set -ue

result=$(
	grep -REn "^[a-zA-Z_]+ = " pikaur --color=always \
	| grep -Ev \
		-e ': Final' \
		\
		-e '\|' \
		-e '(dict|list)\[' \
		-e TypeVar \
		-e namedtuple \
		\
		-e 'create_debug_logger' \
	| sort
)
echo -n "$result"
exit "$(test "$result" = "" && echo 0 || echo 1)"
