# pikaur

Minimalistic AUR helper.


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
	pkg/  # keep built packages; like /var/cache/pacman/pkg/ (optional?)
	db.lck  # transaction lock
~/.config/pikaur.conf  # like /etc/pacman.conf
/tmp/pikaur-$(id -u)/
	build/  # build directory; remove after build (or after whole transaction?)
?	install/  # copy there before installing; remove after transaction
```
