# pikaur

[![Build Status](https://travis-ci.com/actionless/pikaur.svg?branch=master)](https://travis-ci.org/actionless/pikaur) [![Coverage Status](https://coveralls.io/repos/github/actionless/pikaur/badge.svg?branch=master)](https://coveralls.io/github/actionless/pikaur?branch=master)

AUR helper with minimal dependencies. Review PKGBUILDs all in once, next build them all without user interaction.

Inspired by `pacaur`, `yaourt` and `yay`.

Instead of trying to be smarter than pacman (by using `--nodeps`, `--force`, `--ask`, `--noconfirm` and so) it just interactively tells pacman what to do. If pacman asks some unexpected question, the user will be just able to answer it manually.

Notable features:

* build local PKGBUILDs with AUR deps (`-P`/`--pkgbuild`)
* retrieve PKGBUILDs from AUR and ABS (`-G`/`--getpkgbuild`)
* interactively handle common build problems (like untrusted GPG key or checksum mismatch, wrong architecture)
* using [systemd dynamic users](http://0pointer.net/blog/dynamic-users-with-systemd.html "") if building packages as root user
* show unread [Arch news](https://www.archlinux.org/news/ "") before sysupgrade
* [m]anual package selection in [install prompt](#screenshot "") using text editor (ignore unwanted updates or select package provider)
* show AUR package diff and review PKGBUILD and .install files
* [upgrade](#how-to-upgrade-all-the-dev--git-packages-at-once "") `-git`, `-svn` and other dev packages
* AUR package names in shell completion (bash, fish, zsh)
* quickly search&install package by `pikaur <search-query>`

The following pacman operations are extended with AUR capabilities:

* `-S` (build AUR packages, `--needed`, `--ignore` and `--noconfirm` are supported as in pacman, other args are just bypassed to it)
* `-Sw` (build AUR packages but don't install)
* `-Ss` (search or list all AUR packages, `-q` also supported)
* `-Si` (package info)
* `-Su` / `-Syu` (sysupgrade)
* `-Sc` / `-Scc` (build dir/built packages cache clean)
* `-Qu` (query upgradeable, `-q` supported)

Also see `pikaur -Sh`, `-Qh`, `-Ph` and `-Gh` for pikaur-specific flags.

Pikaur wraps all the pacman options accurately except for `-Syu` which is being split into `-Sy` (to refresh package list first) and `-Su` (to install upgrades after user confirmed the package list or altered it via [M]anual package selection).


* [Installation](#installation "")
* [Run without installation](#run-without-installation "")
* [Config file](#configuration "")
* [Directories](#directories "")
* [FAQ](#faq "")
* [Contributing](#contributing "")
* - [Translations](#translations "")
* - [Documentation](#documentation "")
* [Authors](#authors "")


## Installation

```sh
sudo pacman -S --needed base-devel git
git clone https://aur.archlinux.org/pikaur.git
cd pikaur
makepkg -fsri
```

## Screenshot

![Screenshot](https://github.com/actionless/pikaur/blob/master/screenshots/package_update.png "Screenshot")


## Run without installation

```sh
git clone https://github.com/actionless/pikaur.git
cd pikaur
python3 ./pikaur.py -S AUR_PACKAGE_NAME
```



## Configuration

~/.config/pikaur.conf


#### [sync]

##### DevelPkgsExpiration (default: -1)
When doing sysupgrade, count all devel (-git, -svn, -bzr, -hg, -cvs) packages older than N days as being upgradeable.
-1 disables this.
0 means always upgrade.
Passing `--devel` argument will override this option to 0.

##### AlwaysShowPkgOrigin (default: no)
When installing new packages, show their repository name, even if they are coming from one of the official Arch Linux repositories.

##### UpgradeSorting (default: versiondiff)
When upgrading packages, sort them by `versiondiff`, `pkgname` or `repo`.

##### ShowDownloadSize (default: no)
When installing repository packages, show their download size.

##### IgnoreOutofdateAURUpgrades (default: no)
When doing sysupgrade ignore AUR packages which have `outofdate` mark.


#### [build]

##### KeepBuildDir (default: no)
Don't remove `~/.cache/pikaur/build/${PACKAGE_NAME}` directory between the builds.
Will be overridden by `-k/--keepbuild` flag.

##### KeepDevBuildDir (default: yes)
When building dev packages (`-git`, `-svn`, etc),
don't remove `~/.cache/pikaur/build/${PACKAGE_NAME}` directory between the builds.
`No` value will be overridden by `KeepBuildDir` option and `-k/--keepbuild` flag.

##### KeepBuildDeps (default: no)
Don't remove build dependencies between and after the builds.
Will be overridden by `--keepbuilddeps` flag.

##### SkipFailedBuild (default: no)
Always skip the build if it fails and don't show recovery prompt.

##### AlwaysUseDynamicUsers (default: no)
Always isolate the build using systemd dynamic users.
Will be overridden by `--dynamic-users` flag.


#### [review]

##### DontEditByDefault (default: no)
Always default to no when prompting to edit PKGBUILD and install files.

##### NoEdit (default: no)
Don't prompt to edit PKGBUILD and install files.
Will be overridden by `--noedit` and `--edit` flags.

##### NoDiff (default: no)
Don't prompt to show the build files diff.
Will be overridden by `--nodiff` flag.

##### GitDiffArgs (default: --ignore-space-change,--ignore-all-space)
Flags to be passed to `git diff` command when reviewing build files.
Should be separated by commas (`,`).

##### DiffPager (default: auto)
Wherever to use `less` pager when viewing AUR packages diff. Choices are `always`, `auto` or `never`.

##### HideDiffFiles (default: .SRCINFO)
Hide `git diff` for file paths, separated by commas (`,`).


#### [colors]

Terminal colors, from 0 to 15:

##### Version (default: 10)
##### VersionDiffOld (default: 11)
##### VersionDiffNew (default: 9)


#### [ui]

##### RequireEnterConfirm (default: yes)
Require enter key to be pressed when answering questions.

##### PrintCommands (default: no)
Print each command which pikaur is currently spawning.

##### GroupByRepo (default: yes)
Groups official packages by repository when using commands like `pikaur -Ss <query>` or `pikaur <query>`.

##### AurSearchSorting (default: hottest)
Sorting key for AUR packages when using commands like `pikaur -Ss <query>` or `pikaur <query>`. Accepts `hottest`, `numvotes`, `lastmodified`, `popularity`, `pkgname`. Only `pkgname` is sorted ascendingly. The metric for `hottest` is weighted by both `numvotes` and `popularity`.

##### DisplayLastUpdated (default: no)
Display the date a package is last updated on search results when using commands like `pikaur -Ss <query>` or `pikaur <query>`.

##### ReverseSearchSorting (default: no)
Reverse search results of the commands like `pikaur -Ss <query>` or `pikaur <query>`.


#### [misc]

##### PacmanPath (default: pacman)
Path to pacman executable.

##### SudoLoopInterval (default: 59)
Interval in seconds in which `sudo` command will be spawned in the background
to avoid asking for sudo password more than once
(`-1` to disable sudo loop at all).

##### PrivilegeEscalationTool (default: sudo)
A tool used to escalate user privileges. If using `doas` then `persistent` option is required in `doas.conf`. For example:
```
permit persist :wheel
```
Currently supported options are `sudo` and `doas`.


#### [network]

##### AurUrl (default: https://aur.archlinux.org)
AUR Host, useful for users in China to use `https://aur.tuna.tsinghua.edu.cn`.

##### NewsUrl (default: https://www.archlinux.org/feeds/news/)
Arch Linux News URL, useful for users of Parabola or other Arch derivatives.

##### Socks5Proxy (default: )
Specify a socks5 proxy which is used to get AUR package information.

The format is `[host[:port]]`, and the default port is 1080.
PySocks module (`python-pysocks` package) should be installed in order to use this option.

Note that any downloads by `pacman`, `git` or `makepkg` will NOT use this proxy.
If that's needed, setting proxy options in their own config files will take effect
(such as `~/.gitconfig`, `~/.curlrc`).

##### AurHttpProxy (default: )
Specify a HTTP proxy which is used to get AUR package information and to `git`-clone from AUR.

Note that any downloads by `pacman`, `git` (inside the build) or `makepkg` will NOT use this proxy.
If that's needed, setting proxy options in their own config files will take effect
(such as `env HTTP_PROXY=`, `~/.gitconfig`, `~/.curlrc`).

##### AurHttpsProxy (default: )
Specify a HTTPS proxy which is used to get AUR package information and to `git`-clone from AUR.

Note that any downloads by `pacman`, `git` (inside the build) or `makepkg` will NOT use this proxy.
If that's needed, setting proxy options in their own config files will take effect
(such as `env HTTPS_PROXY=`, `~/.gitconfig`, `~/.curlrc`).



## Directories

```sh
~/.cache/pikaur/
├── build/  # build directory (removed after successful build)
├── pkg/  # built packages directory
~/.config/pikaur.conf  # config file
~/.local/share/pikaur/
└── aur_repos/  # keep aur repos there; show diff when updating
    └── last_installed.txt  # aur repo hash of last successfully installed package
```



## FAQ


##### How to upgrade all the dev (-git) packages at once?

`pikaur -Sua --devel --needed`

(`--needed` option will make sure what the same package version won't be rebuilt again and `-a/--aur` will ensure what only AUR packages will be upgraded)


##### How to manually remove unneeded dependencies?

Pikaur is not needed for that, use just Pacman itself:

`sudo pacman -Rs $(pacman -Qtdq)` (however `pikaur -Rs ...` would work as well if you lazy to type `sudo` :) )


##### How to override default source directory, build directory or built package destination?

Set `SRCDEST`, `BUILDDIR` or `PKGDEST` accordingly in `makepkg.conf`.

For more info see `makepkg` documentation.


##### How to clean old or uninstalled AUR packages in ~/.cache/pikaur/pkg?

Use `paccache(8)` with the `--cachedir` option.

To clean them up automatically, you may:

- use a pacman hook.  Start with the provided
  `/usr/share/pikaur/examples/pikaur-cache.hook`, remember to update the
  cache's path.

- use a systemd service & timer (provided `pikaur-cache.service` and
  `pikaur-cache.timer`).  Configure it with `systemctl --user edit
  --full pikaur-cache.service` and activate it with `systemctl --user
  enable --now pikaur-cache.timer`.


##### How to restore original PKGBUILD after editing?

Go to the package's directory, `cd ~/.local/share/pikaur/aur_repos/${PACKAGE_NAME}`.
Review the current PKGBUILD file changes with `git diff` and then reset with  `git checkout -- '*'`.


##### How to see upgrade list without syncing the database? (like "checkupdates" tool from pacman)

Actually use `checkupdates` tool to check the repo updates and use pikaur only for AUR (`-a`/`--aur` switch):

```
checkupdates ; pikaur -Qua 2>/dev/null
```

##### Pikaur slow when running it as root user (or via sudo)

If you find the command takes a long time to initialize, make sure to periodically clear your cache: `pikaur -Scc`. Root pikaur is using SystemD Dynamic Users to isolate build process from the root, and it takes some time to change the owner of build cache to dynamic temporary user.



## Contributing


### Code

You can start from [this list of issues](https://github.com/actionless/pikaur/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22 ""). Grep-ing `@TODO` comments also useful if you're itching to write something.


### Translations

To start working on a new language, say 'uk' (Ukrainian), add it to the
`Makefile` `LANGS` variable and run `make`. Then translate `locale/uk.po` using
your favorite PO editor. Run `make` every time the Python code strings change
or the `.po` is modified.



## Authors

To see the list of authors, use this command inside pikaur git repository directory:

```sh
git log --pretty=tformat:"%an <%ae>" | sort -u
```

### Special thanks

@AladW ([aurutils](https://github.com/AladW/aurutils)), @morganamilo ([yay](https://github.com/Jguer/yay)) during the early stages of Pikaur development.
And [all the other issue contributors](https://github.com/actionless/pikaur/issues?utf8=%E2%9C%93&q=is%3Aissue+-author%3Aactionless) for helping in triaging the bugs and clearing up feature requirements.
