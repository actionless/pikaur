FROM base/archlinux
WORKDIR /opt/app-build/

RUN pacman -Syu --noconfirm && \
    pacman -S --needed --noconfirm python-pylint

COPY . /opt/app-build/
RUN bash ./maintenance_scripts/lint.sh
