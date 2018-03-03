FROM base/archlinux
WORKDIR /opt/app-build/

RUN useradd -m user && \
    echo "root ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
    echo "user ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

RUN pacman -Syu --noconfirm --needed sudo binutils python-pylint

COPY . /opt/app-build/
RUN chown -R user /opt/app-build/
RUN sudo -u user makepkg -fsi --noconfirm
RUN bash ./maintenance_scripts/lint.sh
