#!/bin/bash
set -ue

result=$(
	grep -REn "^[a-zA-Z_]+ = " "$@" --color=always \
	| grep -Ev \
		-e ': Final' \
		-e ' # nonfinal-ignore' \
		\
		-e '=.*\|' \
		-e '=.*(dict|list|Callable)\[' \
		-e TypeVar \
		-e namedtuple \
		\
		-e 'create_logger\(|sudo' \
		\
		-e './maintenance_scripts/find_.*.py.*:.*:' \
		-e '.SRCINFO' \
	| sort
)
echo -n "$result"
exit "$(test "$result" = "" && echo 0 || echo 1)"
