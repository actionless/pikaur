# Licensed under GPLv3, see https://www.gnu.org/licenses/

FROM archlinux:base-devel
WORKDIR /opt/app-build/

ARG GITHUB_TOKEN
ARG GITHUB_RUN_ID
ARG GITHUB_REF

RUN echo 'Server = https://mirrors.xtom.nl/archlinux/$repo/os/$arch' > /etc/pacman.d/mirrorlist ; \
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

RUN echo ">>>> Installing optional pikaur deps:" && \
	pacman -Sy devtools python-pysocks python-defusedxml --noconfirm --needed

COPY ./maintenance_scripts/pikaman.py ./maintenance_scripts/changelog.sh /opt/app-build/maintenance_scripts/
COPY ./packaging/. /opt/app-build/packaging
COPY ./submodules/. /opt/app-build/submodules
COPY ./locale/. /opt/app-build/locale
COPY ./PKGBUILD ./Makefile ./README.md ./pyproject.toml ./.flake8 ./LICENSE /opt/app-build/
COPY ./pikaur_static/. /opt/app-build/pikaur_static
COPY ./pikaur/. /opt/app-build/pikaur
RUN echo ">>>> Preparing build directory:" && \
	chown -R user /opt/app-build/ && \
	echo ">>>> Fetching git tags:" && \
	sudo -u user git fetch -t || true && \
	echo ">>>> Preparing build files:" && \
	sudo -u user tar --transform 's,^,pikaur-git/,' -cf pikaur-git.tar.gz . && \
	sudo -u user sed -i 's/"$pkgname::.*"/"pikaur-git.tar.gz"/' PKGBUILD && \
	echo ">>>> Starting the build:" && \
	./maintenance_scripts/changelog.sh > CHANGELOG && \
	sudo -u user makepkg -fsi --noconfirm && \
	rm -fr ./src/ ./pkg/

COPY ./pikaur_meta_helpers /opt/app-build/pikaur_meta_helpers
#RUN sudo -u user python -um pikaur_meta_helpers.pidowngrade python-coverage '7.4.1-1'  # up to 7.4.4
RUN echo ">>>> Installing test deps using Pikaur itself:" && \
	sudo -u user pikaur -Syu --noconfirm --needed --color=always \
		ruff flake8 python-pylint mypy vulture bandit shellcheck python-coveralls

COPY ./pikaur_test /opt/app-build/pikaur_test
COPY ./maintenance_scripts /opt/app-build/maintenance_scripts/
ARG SKIP_LINTING=0
RUN echo ">>>> Starting CI linting:" && \
	chown -R user /opt/app-build/pikaur_{test,meta_helpers} && \
	if [[ "$SKIP_LINTING" -eq 0 ]] ; then \
		sudo -u user env \
		make lint ; \
	fi

ARG MODE=--local
ARG TESTSUITE=all
RUN echo ">>>> Starting CI testsuite:" && \
	sudo -u user env \
	GITHUB_ACTIONS=1 \
	GITHUB_TOKEN=$GITHUB_TOKEN \
	GITHUB_RUN_ID=$GITHUB_RUN_ID \
	GITHUB_REF=$GITHUB_REF \
	./maintenance_scripts/coverage.sh $MODE --write-db $TESTSUITE
