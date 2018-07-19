# This file is licensed under GPLv3, see https://www.gnu.org/licenses/

FROM base/archlinux
WORKDIR /opt/app-build/
ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

RUN useradd -m user && \
    echo "root ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
    echo "user ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

RUN pacman -Syu --noconfirm --needed sudo base-devel git

COPY . /opt/app-build/
RUN pacman -Sy && \
	chown -R user /opt/app-build/ && \
    sudo -u user git fetch -t || true && \
    sudo -u user tar --transform 's,^,pikaur-git/,' -cf pikaur-git.tar.gz . && \
    sudo -u user sed -i 's/"$pkgname::.*"/"pikaur-git.tar.gz"/' PKGBUILD && \
    sudo -u user makepkg -fsi --noconfirm && \
    sudo -u user pikaur -S --noconfirm python-virtualenv python-pylint flake8 mypy python-vulture --color=always
