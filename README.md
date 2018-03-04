# pikaur

AUR helper with minimal dependencies. Review PKGBUILDs all in once, next build them all without user interaction.

Inspired by `pacaur`, `yaourt` and `yay`.

![Screenshot](https://github.com/actionless/pikaur/blob/master/screenshots/package_update.png "Screenshot")

### Installation

```sh
git clone https://github.com/actionless/pikaur.git
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


### Directories

```sh
~/.cache/pikaur/
├── aur_repos/  # keep there aur repos; show diff when updating
│   └── last_installed.txt  # aur repo hash of last successfully installed package
└── build/  # build directory (removed after successfull build)
~/.config/pikaur.conf  # like /etc/pacman.conf (not implemented yet)
```


### Contributing

#### Translations

To start working on a new language, say 'es' (Spanish), add it to the
`Makefile` `LANGS` variable and run `make`. Then translate `locale/es.po` using
your favorite PO editor. Run `make` every time the Python code strings change
or the `.po` is modified.

Once done, don't forget to distribute the new language by adding it to the
`PKGBUILD` `package()`.
