# This file is licensed under GPLv3, see https://www.gnu.org/licenses/

FROM archlinux/base
WORKDIR /opt/app-build/

RUN pacman -Syu --noconfirm --needed sudo base-devel git && \
	useradd -m user && \
	echo "root ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
	echo "user ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
	echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && \
	echo "LANG=en_US.UTF-8" > /etc/locale.conf && \
	locale-gen
ENV LANG=en_US.utf8 \
	LANGUAGE=en_US.UTF-8 \
	LC_ALL=en_US.UTF-8

COPY . /opt/app-build/
RUN pacman -Sy ruby-ronn asp --noconfirm --needed && \
	chown -R user /opt/app-build/ && \
	sudo -u user git fetch -t || true && \
	sudo -u user make check_man && \
	sudo -u user tar --transform 's,^,pikaur-git/,' -cf pikaur-git.tar.gz . && \
	sudo -u user sed -i 's/"$pkgname::.*"/"pikaur-git.tar.gz"/' PKGBUILD && \
	sudo -u user makepkg -fsi --noconfirm && \
	sudo -u user pikaur -S --noconfirm --color=always python-virtualenv \
		python-pylint flake8 mypy python-vulture python-coveralls \
		python2 python2-setuptools iputils # @TODO: coveralls workaround
