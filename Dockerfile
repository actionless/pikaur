# This file is licensed under GPLv3, see https://www.gnu.org/licenses/

FROM archlinux/base
WORKDIR /opt/app-build/

ARG TRAVIS
ARG TRAVIS_JOB_ID
ARG TRAVIS_BRANCH
ARG TRAVIS_PULL_REQUEST
ARG MODE=--local

RUN echo 'Server = https://mirrors.xtom.nl/archlinux/$repo/os/$arch' >> /etc/pacman.d/mirrorlist ; \
	echo 'Server = https://archlinux.mirror.pcextreme.nl/$repo/os/$arch' >> /etc/pacman.d/mirrorlist ; \
	echo 'Server = https://archlinux.mirror.wearetriple.com/$repo/os/$arch' >> /etc/pacman.d/mirrorlist ; \
	echo 'Server = https://mirror.mijn.host/archlinux/$repo/os/$arch' >> /etc/pacman.d/mirrorlist ; \
	\
	echo '[multilib]' >> /etc/pacman.conf ; \
	echo 'Include = /etc/pacman.d/mirrorlist' >> /etc/pacman.conf
RUN rm /usr/share/libalpm/hooks/package-cleanup.hook ; \
	pacman -Syu --noconfirm --needed sudo base-devel git && \
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
	sleep 0.1 && \
	echo ">>>> Installing test deps using Pikaur itself:" && \
	sudo -u user pikaur -S --noconfirm --color=always iputils python-virtualenv \
		python-pylint flake8 mypy python-vulture python-coveralls shellcheck

RUN echo ">>>> Starting CI testsuite:" && \
	sudo -u user env \
	TRAVIS=$TRAVIS \
	TRAVIS_JOB_ID=$TRAVIS_JOB_ID \
	TRAVIS_BRANCH=$TRAVIS_BRANCH \
	TRAVIS_PULL_REQUEST=$TRAVIS_PULL_REQUEST \
	./maintenance_scripts/ci.sh $MODE --write-db
