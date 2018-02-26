FROM base/archlinux
WORKDIR /opt/app-build/

RUN pacman -Syu --noconfirm --needed python-pylint pyalpm

COPY . /opt/app-build/
RUN bash ./maintenance_scripts/lint.sh
