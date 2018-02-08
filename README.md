# pikaur

AUR helper with minimal dependencies. Review PKGBUILDs all in once, next build them all without user interaction.

Inspired by `pacaur`, `yaourt` and `yay`.

![Screenshot](https://github.com/actionless/pikaur/blob/master/screenshot.png "Screenshot")

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
	aur_repos/  # keep there aur repos; show diff when updating
		last_installed.txt  # aur repo hash of last successfully installed package
	build/  # build directory; (remove after build?)
	pkg/  # keep built packages; like /var/cache/pacman/pkg/ (optional?) (not implemented yet)
	db.lck  # transaction lock (not implemented yet, not sure if needed)
~/.config/pikaur.conf  # like /etc/pacman.conf (not implemented yet)
```
