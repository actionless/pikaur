# Maintainer: Yauhen Kirylau <yawghen AT gmail.com>
# Upstream URL: https://github.com/actionless/oomox

_pkgbase=pikaur
pkgname=pikaur-git
pkgver=0.3
pkgrel=1
pkgdesc="AUR helper with minimal dependencies. Review PKGBUILDs all in once, next build them all without user interaction."
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
	'python'
	'pacman'
	'git'
	'sudo'
)
makedepends=(
	'nuitka'
)

pkgver() {
	cd "${srcdir}/${_pkgbase}"
	git describe | sed 's/^v//;s/-/+/g'
}

build() {
	cd "${srcdir}/${_pkgbase}"
	nuitka --plugin-enable=pylint-warnings --recurse-directory=pikaur --recurse-all ./pikaur.py
}

package() {
	mkdir -p "${pkgdir}/usr/bin/"
	install -D -m755 "${srcdir}/${_pkgbase}/pikaur.exe" "${pkgdir}/usr/bin/pikaur"
}
