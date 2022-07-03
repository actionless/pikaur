# This file is licensed under GPLv3, see https://www.gnu.org/licenses/

FROM archlinux:base-devel
WORKDIR /opt/app-build/

ARG GITHUB_TOKEN
ARG GITHUB_RUN_ID
ARG GITHUB_REF
ARG MODE=--local

RUN echo 'Server = https://mirrors.xtom.nl/archlinux/$repo/os/$arch' >> /etc/pacman.d/mirrorlist ; \
	echo 'Server = https://archlinux.mirror.pcextreme.nl/$repo/os/$arch' >> /etc/pacman.d/mirrorlist ; \
	echo 'Server = https://archlinux.mirror.wearetriple.com/$repo/os/$arch' >> /etc/pacman.d/mirrorlist ; \
	echo 'Server = https://mirror.mijn.host/archlinux/$repo/os/$arch' >> /etc/pacman.d/mirrorlist ; \
	\
	grep '^\[multilib\]' /etc/pacman.conf || echo -e '[multilib]\nInclude = /etc/pacman.d/mirrorlist' >> /etc/pacman.conf
RUN rm /usr/share/libalpm/hooks/package-cleanup.hook ; \
	pacman -Syu --noconfirm --needed sudo base-devel git && \
	(useradd -m user || true) && \
	echo "root ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
	echo "user ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
	echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && \
	echo "LANG=en_US.UTF-8" > /etc/locale.conf && \
	locale-gen
ENV LANG=en_US.utf8 \
	LANGUAGE=en_US.UTF-8 \
	LC_ALL=en_US.UTF-8

COPY . /opt/app-build/
RUN echo ">>>> Installing opt deps:" && \
	pacman -Sy asp python-pysocks --noconfirm --needed && \
	echo ">>>> Preparing build directory:" && \
	chown -R user /opt/app-build/ && \
	echo ">>>> Fetching git tags:" && \
	sudo -u user git fetch -t || true && \
	echo ">>>> Preparing build files:" && \
	sudo -u user tar --transform 's,^,pikaur-git/,' -cf pikaur-git.tar.gz . && \
	sudo -u user sed -i 's/"$pkgname::.*"/"pikaur-git.tar.gz"/' PKGBUILD && \
	echo ">>>> Starting the build:" && \
	sudo -u user makepkg -fsi --noconfirm && \
	rm -fr ./src/ ./pkg/ && \
	sleep 0.1 && \
	echo ">>>> Installing test deps using Pikaur itself:" && \
	sudo -u user pikaur -S --noconfirm --needed --color=always iputils python-virtualenv \
		python-pylint flake8 mypy vulture python-coveralls shellcheck bandit

# workaround broken deps for pylint:
RUN	echo ">>>> Installing test deps using Pikaur itself:" && \
	sudo -u user pikaur -S --noconfirm --needed --color=always python-tomli

RUN echo ">>>> Starting CI testsuite:" && \
	sudo -u user env \
	GITHUB_ACTIONS=1 \
	GITHUB_TOKEN=$GITHUB_TOKEN \
	GITHUB_RUN_ID=$GITHUB_RUN_ID \
	GITHUB_REF=$GITHUB_REF \
	./maintenance_scripts/ci.sh $MODE --write-db
