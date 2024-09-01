#!/usr/bin/env fish

function debug
	echo -e "--> $argv \n"
	command $argv
end

debug \
	nuitka --jobs=(nproc) \
		--plugin-enable=pylint-warnings \
		\
		--include-module=pikaur \
		--include-module=pypyalpm \
		--include-module=pyalpm \
		--include-module=pycman \
		--include-module=pacman_fallback \
		\
		./pikaur-static.py \
		\
		--standalone --onefile \
		--static-libpython=yes \
		--output-filename=pikaur-standalone
