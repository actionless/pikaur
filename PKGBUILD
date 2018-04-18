# Maintainer: Yauheni Kirylau <actionless dot loveless AT gmail.com>
# shellcheck disable=SC2034,SC2154

pkgname=pikaur-git
pkgver=0.10
pkgrel=1
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
	'git'
	'fakeroot'
)
conflicts=('pikaur')

pkgver() {
	cd "${srcdir}/${pkgname}" || exit 2
	set -o pipefail
	git describe | sed 's/^v//;s/-/+/g' || echo 0.0.1
}

build() {
	cd "${srcdir}/${pkgname}" || exit 2
	sed -i -e "s/VERSION.*=.*/VERSION = '${pkgver}'/g" pikaur/config.py
	make
}

package() {
	cd "${srcdir}/${pkgname}" || exit 2
	python setup.py install --prefix=/usr --root="$pkgdir/" --optimize=1
	for lang in fr ru pt de is; do
		install -Dm644 "locale/${lang}.mo" "$pkgdir/usr/share/locale/${lang}/LC_MESSAGES/pikaur.mo"
	done
	install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
	cp -r ./packaging/* "${pkgdir}"
}
