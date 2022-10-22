#!/usr/bin/env bash

filter="cat"
if [[ "${1:-}" = '-c' ]] ; then
	echo "Notable changes:"
	filter="grep -v -i -E \
		-e (typing|typehint|coverage|github|docker|vulture|maintenance_scripts) \
		-e actionless\s[^[:print:]]\[m(doc|chore|test|style|Revert|Merge|refactor)\
		-e [^[:print:]]\[31m[[:print:]]+[^[:print:]]\[m
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
	echo
	echo "Previous release:"
	echo "$result" | tail -n1
fi
