# pikaur

AUR helper with minimal dependencies. Review PKGBUILDs all in once, next build them all without user interaction.

Inspired by `pacaur`, `yaourt` and `yay`.

* [Installation](#installation "")
* [Run without installation](#run-without-installation "")
* [Config file](#configuration "")
* [Directories](#directories "")
* [FAQ](#faq "")
* [Contributing](#contributing "")
* - [Translations](#translations "")

![Screenshot](https://github.com/actionless/pikaur/blob/master/screenshots/package_update.png "Screenshot")


### Installation

```sh
sudo pacman -S --needed base-devel git
git clone https://aur.archlinux.org/pikaur.git
cd pikaur
makepkg -fsri
```


### Run without installation

```sh
git clone https://github.com/actionless/pikaur.git
cd pikaur
python3 ./pikaur.py -Ss AUR_PACKAGE_NAME
python3 ./pikaur.py -S AUR_PACKAGE_NAME
python3 ./pikaur.py -Syu
```



### Configuration

~/.config/pikaur.conf


#### [sync]

##### AlwaysShowPkgOrigin (default: no)
when installing new packages show their repository name even if they are coming from one of the official Arch Linux repositories.

##### DevelPkgsExpiration (default: -1)
when doing sysupgrade count all devel (-git, -svn, -bzr, -hg, -cvs) packages older than N days as being upgradeable.
-1 disables this.
0 means always upgrade.
Passing `--devel` argument will override this option to 1.


#### [build]

##### KeepBuildDir (default: no)
don't remove `~/.cache/pikaur/build/${PACKAGE_NAME}` directory between the builds.

##### NoEdit (default: no)
don't prompt to edit PKGBUILD and install files.


#### [colors]

terminal colors, from 0 to 15

##### Version (default: 10)
##### VersionDiffOld (default: 11)
##### VersionDiffNew (default: 9)


#### [ui]

##### RequireEnterConfirm (default: yes)
require enter key to be pressed when answering questions.






### Directories

```sh
~/.cache/pikaur/
├── aur_repos/  # keep there aur repos; show diff when updating
│   └── last_installed.txt  # aur repo hash of last successfully installed package
├── build/  # build directory (removed after successfull build)
└── pkg/  # built packages directory
~/.config/pikaur.conf  # config file
```

### FAQ

##### How to avoid manually importing GPG keys?

It's recommended to control the keys manually. However if you know what you doing, `keyserver-options auto-key-retrieve` GPG option will automatically import GPG keys.


### Contributing

#### Translations

To start working on a new language, say 'es' (Spanish), add it to the
`Makefile` `LANGS` variable and run `make`. Then translate `locale/es.po` using
your favorite PO editor. Run `make` every time the Python code strings change
or the `.po` is modified.

Once done, don't forget to distribute the new language by adding it to the
`PKGBUILD` `package()`.
