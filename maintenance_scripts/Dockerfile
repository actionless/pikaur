FROM base/archlinux
WORKDIR /opt/app-build/

RUN useradd -m user && \
    echo "root ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
    echo "user ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

RUN pacman -Syu --noconfirm --needed sudo python-pylint pyalpm

COPY . /opt/app-build/
RUN bash ./maintenance_scripts/lint.sh
# check if package can be built:
RUN sudo -u user makepkg -fsi
