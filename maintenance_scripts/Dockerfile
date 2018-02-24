FROM base/archlinux
WORKDIR /opt/app-build/

RUN pacman -Syu --noconfirm --needed --noconfirm python-pylint

COPY . /opt/app-build/
RUN bash ./maintenance_scripts/lint.sh
