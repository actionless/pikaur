FROM base/archlinux
WORKDIR /opt/app-build/

RUN useradd -m user && \
    echo "root ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
    echo "user ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

RUN pacman -Syu --noconfirm --needed sudo base-devel python-pylint git

COPY . /opt/app-build/
RUN chown -R user /opt/app-build/ && \
    sudo -u user git fetch -t &&\
    sudo -u user tar --transform 's,^,pikaur-git/,' -cf pikaur-git.tar.gz . && \
    sudo -u user sed -i 's/"$pkgname::.*"/"pikaur-git.tar.gz"/' PKGBUILD && \
    sudo -u user makepkg -fsi --noconfirm &&\
    sudo -u user pikaur -S --noconfirm mypy --color=always
RUN bash ./maintenance_scripts/lint.sh
