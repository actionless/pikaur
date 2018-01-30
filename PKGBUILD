# Maintainer: Yauhen Kirylau <yawghen AT gmail.com>
# Upstream URL: https://github.com/actionless/oomox

pkgbase=pikaur
pkgname=pikaur-git
pkgver=0.0.1+remove+me
pkgrel=1
pkgdesc="Minimalistic AUR helper."
arch=('any')
url="https://github.com/actionless/pikaur"
license=('GPLv3')
source=(
	"git+https://github.com/actionless/pikaur.git#branch=master"
)
md5sums=(
	"SKIP"
)
depends=(
	'python3'
	'pacman'
	'git'
	'sudo'
)
makedepends=(
	'nuitka'
)

pkgver() {
	cd "${srcdir}/${pkgbase}"
	git describe | sed 's/^v//;s/-/+/g'
}

package() {
	cd "${srcdir}/${pkgbase}"
	nuitka ./pikaur.py
	mkdir -p ${pkgdir}/usr/bin/
	install -D -m755 ./pikaur.exe ${pkgdir}/usr/bin/pikaur
}
