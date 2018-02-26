# Maintainer: Yauheni Kirylau <actionless dot loveless AT gmail.com>
# shellcheck disable=SC2034,SC2154

pkgname=pikaur-git
pkgver=0.6
pkgrel=3
pkgdesc="AUR helper with minimal dependencies. Review PKGBUILDs all in once, next build them all without user interaction."
arch=('any')
url="https://github.com/actionless/pikaur"
license=('GPLv3')
source=(
	"$pkgname::git+https://github.com/actionless/pikaur.git#branch=master"
)
md5sums=(
	"SKIP"
)
depends=(
	'pyalpm'
	'python-setuptools'
	'git'
	'sudo'
	'fakeroot'
)

pkgver() {
	cd "${srcdir}/${pkgname}" || exit 1
	git describe | sed 's/^v//;s/-/+/g'
}

package() {
	cd "${srcdir}/${pkgname}" || exit 1
	sed -i -e "s/VERSION.*=.*/VERSION = '${pkgver}'/g" pikaur/config.py
	python setup.py install --prefix=/usr --root="$pkgdir/" --optimize=1
	install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
