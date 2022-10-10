#!/usr/bin/env bash

filter="cat"
if [[ "${1:-}" = '-c' ]] ; then
	filter="grep -v -i -E \
		-e (typing|typehint|coverage|github|docker|vulture) \
		-e actionless\s[^[:print:]]\[m(doc|chore|test|style|Revert|Merge|refactor)\
	"
	shift
fi

result=$(git log \
	--pretty=tformat:"%Cred%D%Creset %ad %Cgreen%h %Cblue%an %Creset%s" \
	--date='format:%Y-%m-%d' \
	--color=always \
	"$(git tag | grep -v gtk | sort -V | tail -n1)"~1.. \
	"$@" \
)
echo "$result" | $filter
if [[ "${filter}" != "cat" ]] ; then
	echo "$result" | tail -n1
fi
