# pikaur

AUR helper with minimal dependencies. Review PKGBUILDs all in once, next build them all with minimal user interaction.

Inspired by `pacaur`, `yaourt` and `yay`.

* [Installation](#installation "")
* [Run without installation](#run-without-installation "")
* [Config file](#configuration "")
* [Directories](#directories "")

![Screenshot](https://github.com/actionless/pikaur/blob/master/screenshots/package_update.png "Screenshot")


### Installation

```sh
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



### Directories

```sh
~/.cache/pikaur/
├── aur_repos/  # keep there aur repos; show diff when updating
│   └── last_installed.txt  # aur repo hash of last successfully installed package
├── build/  # build directory (removed after successfull build)
└── pkg/  # built packages directory
~/.config/pikaur.conf  # config file
```
