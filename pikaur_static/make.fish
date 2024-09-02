#!/usr/bin/env fish

# Experiment on implementing Makefile-like experience but using fish shell.

# TARGETS: #####################################################################

function _nuitka_common
	_debug \
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
			$argv
end

function normal
	_nuitka_common
end

function standalone
	_nuitka_common \
			--standalone --onefile \
			--static-libpython=yes \
			--output-filename=pikaur-standalone
end

function hello
	pikasay sup
end

function world
	pikasay beaches
end

function script
	_DEPENDS hello world
	echo ! | figlet | pikasay
end

# LIBRARY: #####################################################################

set my_name_is (status filename)

function _debug
	echo -e "--> $argv \n"
	command $argv
end

function print_help
	echo --------
	echo Usage:
	echo "$my_name_is [TARGET]"
	echo --------
	echo Targets:
	echo --------
	for func in (functions --names)
		if test (functions --details $func) = $my_name_is
			echo $func
		end
	end
end

function _DEPENDS
	parallel \
		--halt now,fail=1 \
		-- $my_name_is '{}' \
		::: $argv
end

function _main
	set -f args_length (count $argv)
	if test $args_length -lt 1
		print_help $argv
	else if test $args_length -eq 1
		$argv[1]
	else
		_DEPENDS $argv
	end
end

_main $argv  # this should be at the very bottom

# END ##########################################################################
