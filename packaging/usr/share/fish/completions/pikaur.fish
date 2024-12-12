# Completions for pikaur
# Author: Yauhen Kirylau <actionless DOT loveless PLUS aur AT gmail MF com>

# Based on completions for pacman
# Author: Giorgio Lando <patroclo7@gmail.com>
# Updated by maxfl, SanskritFritz, faho, f1u77y

function __fish_pikaur_print_packages
    switch (commandline -ct)
        case '-**'
            return
    end

    #Get the word 'Package' in the current language
    set -l package (_ "Package")

    # Set up cache directory
    if test -z "$XDG_CACHE_HOME"
        set XDG_CACHE_HOME $HOME/.cache
    end
	mkdir -m 700 -p $XDG_CACHE_HOME

	set cache_file $XDG_CACHE_HOME/.pikaur-cache.$USER
	if test -f $cache_file
		cat $cache_file
		set age (math (date +%s) - (stat -c '%Y' $cache_file))
		set max_age 250
		if test $age -lt $max_age
			return
		end
	end

	# prints: <package name>	Package
	pikaur -Ssq | tail -n +2 | sed -e 's/$/\t'$package'/' >$cache_file &
	return
end

set -l progname pikaur

set -l listinstalled "(pacman -Q | string replace ' ' \t)"
# This might be an issue if another package manager is also installed (e.g. for containers)
set -l listall "(__fish_pikaur_print_packages)"
set -l listrepos "(__fish_print_pacman_repos)"
set -l listgroups "(pikaur -Sg)\t'Package Group'"

###############################################################################
set -l noopt 'not __fish_contains_opt -s S -s D -s Q -s R -s U -s T -s F -s P -s G database query sync remove upgrade deptest files pkgbuild getpkgbuild'
set -l pkgbuild '__fish_contains_opt -s P pkgbuild'
set -l getpkgbuild '__fish_contains_opt -s G getpkgbuild'
###############################################################################
set -l database '__fish_contains_opt -s D database'
set -l query '__fish_contains_opt -s Q query'
set -l remove '__fish_contains_opt -s R remove'
set -l sync '__fish_contains_opt -s S sync'
set -l upgrade '__fish_contains_opt -s U upgrade'
set -l files '__fish_contains_opt -s F files'

complete -c pikaur -e
complete -c pikaur -f
# HACK: We only need these two to coerce fish to stop file completion and complete options
complete -c $progname -n $noopt -a "-D" -d "Modify the package database"
complete -c $progname -n $noopt -a "-Q" -d "Query the package database"
# Primary operations
complete -c $progname -s D -f -l database -n $noopt -d 'Modify the package database'
complete -c $progname -s Q -f -l query -n $noopt -d 'Query the package database'
complete -c $progname -s R -f -l remove -n $noopt -d 'Remove packages from the system'
complete -c $progname -s S -f -l sync -n $noopt -d 'Synchronize packages'
complete -c $progname -s T -f -l deptest -n $noopt -d 'Check dependencies'
complete -c $progname -s U -f -l upgrade -n $noopt -d 'Upgrade or add a local package'
complete -c $progname -s F -f -l files -n $noopt -d 'Query the files database'
complete -c $progname -s V -f -l version -d 'Display version and exit'
complete -c $progname -s h -f -l help -d 'Display help'
###############################################################################
complete -c $progname -s P -f -l pkgbuild -n $noopt -d 'Build local PKGBUILDs with AUR deps'
complete -c $progname -n "$pkgbuild" -xa '(__fish_complete_suffix "*")' -d 'PKGBUILD'
complete -c $progname -s G -f -l getpkgbuild -n $noopt -d 'Download PKGBUILDs from AUR or ABS'
complete -c $progname -n "$getpkgbuild" -xa "$listall"
###############################################################################

# General options
# Only offer these once a command has been given so they get prominent display
complete -c $progname -n "not $noopt" -s b -l dbpath -d 'Alternative database location' -xa '(__fish_complete_directories)'
complete -c $progname -n "not $noopt" -s r -l root -d 'Alternative installation root'
complete -c $progname -n "not $noopt" -s v -l verbose -d 'Output more status messages'
complete -c $progname -n "not $noopt" -l arch -d 'Alternate architecture' -f
complete -c $progname -n "not $noopt" -l cachedir -d 'Alternative package cache location'
complete -c $progname -n "not $noopt" -l config -d 'Alternate config file'
complete -c $progname -n "not $noopt" -l gpgdir -d 'GPG directory to verify signatures'
complete -c $progname -n "not $noopt" -l hookdir -d 'Hook file directory'
complete -c $progname -n "not $noopt" -l logfile -d 'Specify alternative log file'
complete -c $progname -n "not $noopt" -l noconfirm -d 'Bypass any question' -f


###############################################################################
for condition in pkgbuild
	complete -c $progname -n $$condition -s i -l install -d 'Install built package' -f
end

for condition in sync pkgbuild
	complete -c $progname -n $$condition -l noedit -d 'Bypass editing PKGBUILDs' -f
	complete -c $progname -n $$condition -l edit -d 'Edit PKGBUILDs' -f
	complete -c $progname -n $$condition -s k -l keepbuild -d "Don't remove build dir after the build" -f
	complete -c $progname -n $$condition -l rebuild -d "Always rebuild AUR packages" -f
	complete -c $progname -n $$condition -l mflags -x -d "CLI args to pass to makepkg" -f
	complete -c $progname -n $$condition -l makepkg-config -xa '(__fish_complete_suffix ".conf")' -d "path to custom makepkg config" -f
	complete -c $progname -n $$condition -l makepkg-path -xa '(__fish_complete_suffix "*")' -d "override path to makepkg executable" -f
end

for condition in sync
	complete -c $progname -n $$condition -l namesonly -d "Search only in package names" -f
	complete -c $progname -n $$condition -l devel -d "always sysupgrade '-git', '-svn' and other dev packages" -f
	complete -c $progname -n $$condition -l nodiff -d "don't prompt to show the build files diff" -f
end

for condition in sync query
	complete -c $progname -n $$condition -s a -l aur -d 'Query packages from AUR only' -f
	complete -c $progname -n $$condition -s r -l repo -d 'Query packages from repo only' -f
end
###############################################################################

# Transaction options (sync, remove, upgrade)
for condition in sync remove upgrade
    complete -c $progname -n $$condition -s d -l nodeps -d 'Skip [all] dependency checks' -f
    complete -c $progname -n $$condition -l dbonly -d 'Modify database entry only' -f
    complete -c $progname -n $$condition -l noprogressbar -d 'Do not display progress bar' -f
    complete -c $progname -n $$condition -l noscriptlet -d 'Do not execute install script' -f
    complete -c $progname -n $$condition -s p -l print -d 'Dry run, only print targets' -f
    complete -c $progname -n $$condition -l print-format -x -d 'Specify printf-like format' -f
end

# Database and upgrade options (database, sync, upgrade)
for condition in database sync upgrade
    complete -c $progname -n $$condition -l asdeps -d 'Mark PACKAGE as dependency' -f
    complete -c $progname -n $$condition -l asexplicit -d 'Mark PACKAGE as explicitly installed' -f
end

# Upgrade options (sync, upgrade)
for condition in sync upgrade
    complete -c $progname -n $$condition -l force -d 'Bypass file conflict checks' -f
    complete -c $progname -n $$condition -l ignore -d 'Ignore upgrade of PACKAGE' -xa "$listinstalled" -f
    complete -c $progname -n $$condition -l ignoregroup -d 'Ignore upgrade of GROUP' -xa "$listgroups" -f
    complete -c $progname -n $$condition -l needed -d 'Do not reinstall up-to-date targets' -f
    complete -c $progname -n $$condition -l recursive -d 'Recursively reinstall all dependencies' -f
end

# Query and sync options
for condition in query sync
    complete -c $progname -n $$condition -s g -l groups -d 'Display all packages in GROUP' -xa "$listgroups" -f
    complete -c $progname -n $$condition -s i -l info -d 'Display information on PACKAGE' -f
    complete -c $progname -n $$condition -s q -l quiet -d 'Show less information' -f
    complete -c $progname -n $$condition -s s -l search -r -d 'Search packages for regexp' -f
end

# Query options
complete -c $progname -n $query -s c -l changelog -d 'View the change log of PACKAGE' -f
complete -c $progname -n $query -s d -l deps -d 'List only non-explicit packages (dependencies)' -f
complete -c $progname -n $query -s e -l explicit -d 'List only explicitly installed packages' -f
complete -c $progname -n $query -s k -l check -d 'Check if all files owned by PACKAGE are present' -f
complete -c $progname -n $query -s l -l list -d 'List all files owned by PACKAGE' -f
complete -c $progname -n $query -s m -l foreign -d 'List all packages not in the database' -f
complete -c $progname -n $query -s o -l owns -r -d 'Search for the package that owns FILE'
complete -c $progname -n $query -s p -l file -d 'Apply the query to a package file, not package'
complete -c $progname -n $query -s t -l unrequired -d 'List only unrequired packages' -f
complete -c $progname -n $query -s u -l upgrades -d 'List only out-of-date packages' -f
complete -c $progname -n "$query" -d 'Installed package' -xa $listinstalled -f

# Remove options
complete -c $progname -n $remove -s c -l cascade -d 'Also remove packages depending on PACKAGE' -f
complete -c $progname -n $remove -s n -l nosave -d 'Ignore file backup designations' -f
complete -c $progname -n $remove -s s -l recursive -d 'Also remove dependencies of PACKAGE' -f
complete -c $progname -n $remove -s u -l unneeded -d 'Only remove targets not required by PACKAGE' -f
complete -c $progname -n "$remove" -d 'Installed package' -xa $listinstalled -f

# Sync options
complete -c $progname -n $sync -s c -l clean -d 'Remove [all] packages from cache'
complete -c $progname -n $sync -s l -l list -xa "$listrepos" -d 'List all packages in REPOSITORY'
complete -c $progname -n "$sync; and not __fish_contains_opt -s u sysupgrade" -s u -l sysupgrade -d 'Upgrade all packages that are out of date'
complete -c $progname -n "$sync; and __fish_contains_opt -s u sysupgrade" -s u -l sysupgrade -d 'Also downgrade packages'
complete -c $progname -n $sync -s w -l downloadonly -d 'Only download the target packages'
complete -c $progname -n $sync -s y -l refresh -d 'Download fresh copy of the package list'
complete -c $progname -n "$sync" -xa "$listall $listgroups"

# Database options
set -l has_db_opt '__fish_contains_opt asdeps asexplicit'
complete -c $progname -n "$database; and not $has_db_opt" -xa --asdeps -d 'Mark PACKAGE as dependency'
complete -c $progname -n "$database; and not $has_db_opt" -xa --asexplicit -d 'Mark PACKAGE as explicitly installed'
complete -c $progname -n "$database; and not $has_db_opt" -s k -l check -d 'Check database validity'
complete -c $progname -n "$has_db_opt; and $database" -xa "$listinstalled"

# File options - since pacman 5
set -l has_file_opt '__fish_contains_opt list search -s l -s s'
complete -c $progname -n "$files; and not $has_file_opt" -xa --list -d 'List files owned by given packages'
complete -c $progname -n "$files; and not $has_file_opt" -xa -l -d 'List files owned by given packages'
complete -c $progname -n "$files; and not $has_file_opt" -xa --search -d 'Search packages for matching files'
complete -c $progname -n "$files; and not $has_file_opt" -xa -s -d 'Search packages for matching files'
complete -c $progname -n "$files" -s y -l refresh -d 'Refresh the files database' -f
complete -c $progname -n "$files" -s l -l list -d 'List files owned by given packages' -xa $listall
complete -c $progname -n "$files" -s s -l search -d 'Search packages for matching files'
complete -c $progname -n "$files" -s o -l owns -d 'Search for packages that include the given files'
complete -c $progname -n "$files" -s q -l quiet -d 'Show less information' -f
complete -c $progname -n "$files" -l machinereadable -d 'Show in machine readable format: repo\0pkgname\0pkgver\0path\n' -f

# Upgrade options
# Theoretically, pacman reads packages in all formats that libarchive supports
complete -c $progname -n "$upgrade" -xa '(__fish_complete_suffix "pkg.tar*")' -d 'Package file'
