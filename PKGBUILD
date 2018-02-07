# Maintainer: Yauhen Kirylau <yawghen AT gmail.com>
# Upstream URL: https://github.com/actionless/oomox

app_name=pikaur
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
	cd "${srcdir}/${app_name}"
	git describe | sed 's/^v//;s/-/+/g'
}

build() {
	cd "${srcdir}/${app_name}"
	nuitka --plugin-enable=pylint-warnings --recurse-directory=pikaur --recurse-all ./pikaur.py
}

package() {
	cp -r ${srcdir}/${app_name}/packaging/* ${pkgdir}
	mkdir -p "${pkgdir}/usr/bin/"
	install -D -m755 "${srcdir}/${app_name}/pikaur.exe" "${pkgdir}/usr/bin/pikaur"
}
