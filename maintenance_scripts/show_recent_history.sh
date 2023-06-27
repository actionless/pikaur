#!/usr/bin/env bash
set -euo pipefail

style="default"
if [[ "${1:-}" = '-c' ]] ; then
	style="compact"
	shift
fi

result=$(git log \
	--graph \
	--pretty=tformat:"%Cred%D%Creset %ad %Cgreen%h %Cblue%an %Creset%s" \
	--date='format:%Y-%m-%d' \
	--color=always \
	"$(git tag | grep -v gtk | sort -V | tail -n1)"~1.. \
	"$@" \
)
if [[ "${style}" = "compact" ]] ; then
	echo "Notable changes:"
	echo "$result" \
	| grep -v -i -E \
		-e "(typing|typehint|coverage|github|docker|vulture|maintenance_scripts|fixup)" \
		-e "actionless\s[^[:print:]]\[m(doc|chore|test|style|Revert|Merge|refactor|feat\(test|fix\(test)" \
	| sed \
		-E "s/[^[:print:]]\[31m[[:print:]]+[^[:print:]]\[m//g"
	echo
	echo "Previous release:"
	echo "$result" | tail -n1
else
	echo "$result"
fi
