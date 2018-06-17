# pylint: disable=too-many-lines
import sys
import os
import hashlib
from multiprocessing.pool import ThreadPool
from tempfile import NamedTemporaryFile
from typing import List, Dict, Optional

import pyalpm

from .i18n import _
from .config import PikaurConfig
from .args import reconstruct_args, PikaurArgs
from .aur import find_aur_packages, strip_aur_repo_name
from .aur_deps import find_aur_deps, find_repo_deps_of_aur_pkgs
from .pacman import (
    OFFICIAL_REPOS,
    PackageDB, PacmanConfig,
    get_pacman_command, refresh_pkg_db, find_upgradeable_packages,
)
from .package_update import (
    PackageUpdate,
    get_remote_package_version, find_aur_updates,
)
from .exceptions import (
    PackagesNotFoundInAUR, DependencyVersionMismatch,
    BuildError, CloneError, DependencyError, DependencyNotBuiltYet,
    SysExit,
)
from .build import PackageBuild, clone_aur_repos
from .makepkg_config import MakepkgConfig
from .pprint import (
    color_line, bold_line,
    print_stderr, print_stdout,
)
from .print_department import (
    pretty_format_sysupgrade, pretty_format_upgradeable,
    print_not_found_packages,
)
from .core import (
    PackageSource,
    interactive_spawn, remove_dir, open_file, sudo, get_editor,
)
from .conflicts import find_aur_conflicts
from .prompt import (
    ask_to_continue, retry_interactive_command,
    retry_interactive_command_or_exit, get_input,
)
from .version import VersionMatcher
from .srcinfo import SrcInfo
from .news import News


def print_ignored_package(package_name):
    current = PackageDB.get_local_dict().get(package_name)
    current_version = current.version if current else ''
    new_version = get_remote_package_version(package_name)
    print_stderr('{} {}'.format(
        color_line('::', 11),
        _("Ignoring package {}").format(
            pretty_format_upgradeable(
                [PackageUpdate(
                    name=package_name,
                    current_version=current_version,
                    new_version=new_version or '',
                    package=None,
                )],
                template=(
                    "{pkg_name} ({current_version} => {new_version})"
                    if current_version else
                    "{pkg_name} {new_version}"
                )
            ))
    ))


def print_package_uptodate(package_name: str, package_source: PackageSource) -> None:
    print_stderr(
        '{} {}'.format(
            color_line(_("warning:"), 11),
            _("{name} {version} {package_source} package is up to date - skipping").format(
                name=package_name,
                version=bold_line(
                    PackageDB.get_local_dict()[package_name].version
                ),
                package_source=package_source.name
            )
        )
    )


def _check_pkg_arch(pkgbuild):
    src_info = SrcInfo(pkgbuild.repo_path)
    arch = MakepkgConfig.get('CARCH')
    supported_archs = src_info.get_values('arch')
    if supported_archs and (
            'any' not in supported_archs
    ) and (
        arch not in supported_archs
    ):
        print_stderr("{} {}".format(
            color_line(':: error:', 9),
            _("{name} can't be built on the current arch ({arch}). "
              "Supported: {suparch}").format(
                  name=bold_line(', '.join(pkgbuild.package_names)),
                  arch=arch,
                  suparch=', '.join(supported_archs))
        ))
        sys.exit(95)
    pkgbuild.reviewed = True


def hash_file(filename):
    md5 = hashlib.md5()
    with open(filename, 'rb') as file:
        eof = False
        while not eof:
            data = file.read(1024)
            if data:
                md5.update(data)
            else:
                eof = True
    return md5.hexdigest()


class InstallPackagesCLI():
    # @TODO: refactor this warning:
    # pylint: disable=too-many-public-methods,too-many-instance-attributes

    # User input
    args: PikaurArgs
    install_package_names: List[str]
    manually_excluded_packages_names: List[str]
    resolved_conflicts: List[List[str]]

    # computed package lists:
    not_found_repo_pkgs_names: List[str]
    found_conflicts: Dict[str, List[str]]
    repo_packages_by_name: Dict[str, pyalpm.Package]
    aur_deps_relations: Dict[str, List[str]]
    # pkgbuilds from cloned aur repos:
    package_builds_by_name: Dict[str, PackageBuild]

    # Packages' install info
    # @TODO: refactor this and related methods
    #        into separate class InstallPrompt? (PackageSelection?)
    repo_packages_install_info: List[PackageUpdate]
    new_repo_deps_install_info: List[PackageUpdate]
    thirdparty_repo_packages_install_info: List[PackageUpdate]
    new_thirdparty_repo_deps_install_info: List[PackageUpdate]
    aur_updates_install_info: List[PackageUpdate]
    aur_deps_install_info: List[PackageUpdate]

    # Installation results
    # transactions by PackageSource(AUR/repo), direction(removed/installed):
    transactions: Dict[str, Dict[str, List[str]]]
    # AUR packages which failed to build:
    # @TODO: refactor to store in transactions
    failed_to_build_package_names: List[str]

    # arch news
    news: Optional[News] = None

    def __init__(self, args: PikaurArgs) -> None:
        self.args = args
        self.install_package_names = self.args.positional[:]

        self.manually_excluded_packages_names = []
        self.resolved_conflicts = []

        self.not_found_repo_pkgs_names = []
        self.repo_packages_by_name = {}
        self.aur_deps_relations = {}
        self.package_builds_by_name = {}

        self.found_conflicts = {}
        self.transactions = {}
        self.failed_to_build_package_names = []

        if not self.args.aur:
            with ThreadPool() as pool:
                pool.apply_async(refresh_pkg_db, (self.args, ))
                if self.news:
                    pool.apply_async(self.news.fetch_latest, ())
                pool.close()
                pool.join()
            if self.args.refresh:
                PackageDB.discard_repo_cache()

        if self.args.sysupgrade and not args.repo:
            print_stdout('{} {}'.format(
                color_line('::', 12),
                bold_line(_("Starting full AUR upgrade..."))
            ))
        if not self.args.aur:
            if self.args.sysupgrade:
                self.news = News()
        else:
            self.not_found_repo_pkgs_names = self.install_package_names
            self.install_package_names = []

        self.get_all_packages_info()
        if self.news:
            self.news.print_news()
        if not self.args.noconfirm:
            self.install_prompt()

        self.get_package_builds()
        # @TODO: ask to install optdepends (?)
        if not self.args.downloadonly:
            self.ask_about_package_conflicts()
        self.review_build_files()

        self.install_packages()

    @property
    def aur_packages_names(self) -> List[str]:
        return list(self.aur_deps_relations.keys())

    @property
    def aur_deps_names(self) -> List[str]:
        _aur_deps_names: List[str] = []
        for deps in self.aur_deps_relations.values():
            _aur_deps_names += deps
        return list(set(_aur_deps_names))

    @property
    def all_aur_packages_names(self) -> List[str]:
        return list(set(self.aur_packages_names + self.aur_deps_names))

    def get_editor(self) -> Optional[List[str]]:
        editor = get_editor()
        if not editor and self.ask_to_continue(_("Do you want to proceed without editing?")):
            sys.exit(125)
        return editor

    def exclude_ignored_packages(self, package_names: List[str]) -> None:
        ignored_packages = []
        for pkg_name in package_names[:]:
            if self.package_is_ignored(pkg_name):
                package_names.remove(pkg_name)
                ignored_packages.append(pkg_name)

        for package_name in ignored_packages:
            print_ignored_package(package_name)

    def get_all_packages_info(self) -> None:  # pylint:disable=too-many-branches
        """
        Retrieve info (`PackageUpdate` objects) of packages
        which are going to be installed/upgraded and their dependencies
        """

        # deal with package names which user explicitly wants to install
        self.exclude_ignored_packages(self.install_package_names)
        self.repo_packages_by_name = {}

        # retrieve PackageUpdate objects for repo packages to be installed
        # and their upgrades if --sysupgrade was passed
        self.repo_packages_install_info = []
        self.new_repo_deps_install_info = []
        self.thirdparty_repo_packages_install_info = []
        self.new_thirdparty_repo_deps_install_info = []
        self.aur_updates_install_info = []
        self.aur_deps_install_info = []

        for pkg_name in self.manually_excluded_packages_names:
            if pkg_name in self.install_package_names:
                self.install_package_names.remove(pkg_name)

        if not self.args.aur:
            self.get_repo_pkgs_info()

        # retrieve PackageUpdate objects for AUR packages to be installed
        # and their upgrades if --sysupgrade was passed
        if not self.args.repo:
            self.get_aur_pkgs_info(self.not_found_repo_pkgs_names)
        elif self.not_found_repo_pkgs_names:
            print_not_found_packages(self.not_found_repo_pkgs_names, repo=True)

        # check if we really need to build/install anything
        if not (
                self.repo_packages_install_info or
                self.thirdparty_repo_packages_install_info or
                self.aur_updates_install_info
        ):
            print_stdout('{} {}'.format(
                color_line('::', 10),
                _("Nothing to do."),
            ))
            sys.exit(0)

        # try to find AUR deps for AUR packages
        # if some exception wasn't handled inside -- just write message and exit
        try:
            self.get_aur_deps_info()
        except PackagesNotFoundInAUR as exc:
            if exc.wanted_by:
                print_stderr("{} {}".format(
                    color_line(':: error:', 9),
                    bold_line(
                        _("Dependencies missing for {}").format(', '.join(exc.wanted_by)))
                ))
            print_not_found_packages(exc.packages)
            sys.exit(131)
        except DependencyVersionMismatch as exc:
            print_stderr(color_line(_("Version mismatch:"), 11))
            print_stderr(
                _("{what} depends on: '{dep}'\n found in '{location}': '{version}'").format(
                    what=bold_line(exc.who_depends),
                    dep=exc.dependency_line,
                    location=exc.location,
                    version=exc.version_found,
                )
            )
            sys.exit(131)

        self.get_repo_deps_info()

        # update package info to show deps in prompt:
        all_install_infos = (
            self.repo_packages_install_info +
            self.thirdparty_repo_packages_install_info +
            self.new_repo_deps_install_info +
            self.new_thirdparty_repo_deps_install_info +
            self.aur_updates_install_info +
            self.aur_deps_install_info
        )
        all_deps_install_infos = (
            self.new_repo_deps_install_info +
            self.new_thirdparty_repo_deps_install_info +
            self.aur_deps_install_info
        )
        for pkg_install_info in all_install_infos:
            for dep_install_info in all_deps_install_infos:
                for name_and_version in (
                        [dep_install_info.package.name, ] +  # type: ignore
                        (dep_install_info.package.provides or [])
                ):
                    name = VersionMatcher(name_and_version).pkg_name
                    if name in [
                            VersionMatcher(dep_line).pkg_name
                            for dep_line in pkg_install_info.package.depends
                    ]:
                        if not dep_install_info.required_by:
                            dep_install_info.required_by = []
                        dep_install_info.required_by.append(pkg_install_info)

    def package_is_ignored(self, package_name: str) -> bool:
        if (
                package_name in (
                    (self.args.ignore or []) + PacmanConfig().options.get('IgnorePkg', [])
                )
        ) and not (
            package_name in self.install_package_names or
            package_name in self.not_found_repo_pkgs_names
        ):
            return True
        return False

    def _get_repo_pkgs_info(  # pylint: disable=too-many-locals
            self, pkg_names: List[str], extra_args: Optional[List[str]] = None
    ) -> List[PackageUpdate]:
        extra_args = extra_args or []
        all_repo_pkgs = PackageDB.get_repo_dict()
        all_local_pkgs = PackageDB.get_local_dict()

        pacman_args = get_pacman_command(self.args) + [
            '--sync',
        ] + reconstruct_args(self.args, ignore_args=[
            'sync',
            'refresh',
            'ignore',
            'sysupgrade',
        ])

        pkg_install_infos = []
        all_results = {}
        with ThreadPool() as pool:
            all_requests = {}
            for pkg_name in pkg_names[:]:
                all_requests[pkg_name] = pool.apply_async(
                    PackageDB.get_print_format_output,
                    (pacman_args + [pkg_name], )
                )
            pool.close()
            pool.join()
            for pkg_name, request in all_requests.items():
                all_results[pkg_name] = request.get()
        for pkg_name, results in all_results.items():
            if not results:
                self.not_found_repo_pkgs_names.append(pkg_name)
                if pkg_name in self.install_package_names:
                    self.install_package_names.remove(pkg_name)
            else:
                for pkg_print in results:
                    pkg = all_repo_pkgs[pkg_print.full_name]
                    local_pkg = all_local_pkgs.get(pkg.name)
                    install_info = PackageUpdate(
                        name=pkg.name,
                        current_version=local_pkg.version if local_pkg else '',
                        new_version=pkg.version,
                        description=pkg.desc,
                        repository=pkg.db.name,
                        package=pkg,
                    )

                    provides = install_info.package.provides
                    providing_for = [
                        pkg_name for pkg_name in [
                            VersionMatcher(prov).pkg_name
                            for prov in provides
                        ]
                        if pkg_name in self.install_package_names
                    ] if provides else []
                    if providing_for:
                        install_info.name = providing_for[0]
                        install_info.provided_by = [
                            provided_dep.package for provided_dep in
                            PackageDB.get_repo_provided_dict()[providing_for[0]]
                        ]
                        install_info.new_version = ''

                    groups = install_info.package.groups
                    members_of = [
                        gr for gr in groups
                        if gr in self.install_package_names
                    ]
                    if members_of:
                        install_info.members_of = members_of

                    pkg_install_infos.append(install_info)
        return pkg_install_infos

    def get_upgradeable_repo_pkgs_info(self) -> List[PackageUpdate]:
        if not self.args.sysupgrade:
            return []
        all_local_pkgs = PackageDB.get_local_dict()
        pkg_install_infos = []
        for pkg in find_upgradeable_packages():
            local_pkg = all_local_pkgs.get(pkg.name)
            install_info = PackageUpdate(
                name=pkg.name,
                current_version=local_pkg.version if local_pkg else '',
                new_version=pkg.version,
                description=pkg.desc,
                repository=pkg.db.name,
                package=pkg,
            )
            pkg_install_infos.append(install_info)
        return pkg_install_infos

    def get_repo_pkgs_info(self):
        for pkg_update in (
                self._get_repo_pkgs_info(pkg_names=self.install_package_names) +
                self.get_upgradeable_repo_pkgs_info()
        ):
            if pkg_update.name in [
                    install_info.name for install_info in
                    (
                        self.repo_packages_install_info +
                        self.thirdparty_repo_packages_install_info +
                        self.new_repo_deps_install_info +
                        self.new_thirdparty_repo_deps_install_info
                    )
            ]:
                continue

            pkg_name = pkg_update.name
            if (
                    pkg_name in self.manually_excluded_packages_names
            ) or (
                self.package_is_ignored(pkg_name)
            ):
                print_ignored_package(pkg_name)
                # if pkg_name not in self.manually_excluded_packages_names:
                    # self.manually_excluded_packages_names.append(pkg_name)
                continue

            if pkg_update.current_version == '' and (
                    (
                        pkg_name not in self.install_package_names
                    ) and (not pkg_update.provided_by) and (not pkg_update.members_of)
            ):
                if pkg_update.repository in OFFICIAL_REPOS:
                    self.new_repo_deps_install_info.append(pkg_update)
                else:
                    self.new_thirdparty_repo_deps_install_info.append(pkg_update)
                continue
            if pkg_update.repository in OFFICIAL_REPOS:
                self.repo_packages_install_info.append(pkg_update)
            else:
                self.thirdparty_repo_packages_install_info.append(pkg_update)

    def get_repo_deps_info(self) -> None:
        all_aur_pkg_names = [
            pkg_info.name for pkg_info in self.aur_updates_install_info + self.aur_deps_install_info
        ]
        new_dep_names = find_repo_deps_of_aur_pkgs(all_aur_pkg_names)

        for dep_install_info in self._get_repo_pkgs_info(
                pkg_names=new_dep_names, extra_args=['--needed']
        ):
            if dep_install_info.name in [
                    install_info.name for install_info in
                    (self.new_repo_deps_install_info + self.new_thirdparty_repo_deps_install_info)
            ]:
                continue
            if dep_install_info.repository in OFFICIAL_REPOS:
                self.new_repo_deps_install_info.append(dep_install_info)
            else:
                self.new_thirdparty_repo_deps_install_info.append(dep_install_info)

    def get_aur_pkgs_info(self, aur_packages_names: List[str]):
        local_pkgs = PackageDB.get_local_dict()
        aur_pkg_list, not_found_aur_pkgs = find_aur_packages(aur_packages_names)
        if not_found_aur_pkgs:
            print_not_found_packages(sorted(not_found_aur_pkgs))
            sys.exit(6)
        aur_pkgs = {
            aur_pkg.name: aur_pkg
            for aur_pkg in aur_pkg_list
        }
        aur_updates_install_info_by_name: Dict[str, PackageUpdate] = {}
        if self.args.sysupgrade:
            aur_updates_list, not_found_aur_pkgs = find_aur_updates(self.args)
            self.exclude_ignored_packages(not_found_aur_pkgs)
            if not_found_aur_pkgs:
                print_not_found_packages(sorted(not_found_aur_pkgs))
            aur_updates_install_info_by_name = {
                upd.name: upd for upd in aur_updates_list
            }
        for pkg_name, aur_pkg in aur_pkgs.items():
            if pkg_name in aur_updates_install_info_by_name:
                continue
            local_pkg = local_pkgs.get(pkg_name)
            aur_updates_install_info_by_name[pkg_name] = PackageUpdate(
                name=pkg_name,
                current_version=local_pkg.version if local_pkg else ' ',
                new_version=aur_pkg.version,
                description=aur_pkg.desc,
                package=aur_pkg,
            )
        for pkg_name in list(aur_updates_install_info_by_name.keys())[:]:
            if (
                    pkg_name in self.manually_excluded_packages_names
            ) or (
                self.package_is_ignored(pkg_name)
            ):
                print_ignored_package(pkg_name)
                del aur_updates_install_info_by_name[pkg_name]
        self.aur_updates_install_info = list(aur_updates_install_info_by_name.values())

    def get_aur_deps_info(self):
        all_aur_packages_names = [info.name for info in self.aur_updates_install_info]
        if all_aur_packages_names:
            print_stdout(_("Resolving AUR dependencies..."))
        try:
            self.aur_deps_relations = find_aur_deps(all_aur_packages_names)
        except DependencyVersionMismatch as exc:
            if exc.location is not PackageSource.LOCAL:
                raise exc
            # if local package is too old
            # let's see if a newer one can be found in AUR:
            pkg_name = exc.depends_on
            _aur_pkg_list, not_found_aur_pkgs = find_aur_packages([pkg_name, ])
            if not_found_aur_pkgs:
                raise exc
            # start over computing deps and include just found AUR package:
            self.install_package_names.append(pkg_name)
            self.get_all_packages_info()
            return
        # prepare install info (PackageUpdate objects)
        # for all the AUR packages which gonna be built:
        aur_pkgs = {
            aur_pkg.name: aur_pkg
            for aur_pkg in find_aur_packages(self.aur_deps_names)[0]
        }
        local_pkgs = PackageDB.get_local_dict()
        for pkg_name in self.aur_deps_names:
            aur_pkg = aur_pkgs[pkg_name]
            local_pkg = local_pkgs.get(pkg_name)
            self.aur_deps_install_info.append(PackageUpdate(
                name=pkg_name,
                current_version=local_pkg.version if local_pkg else ' ',
                new_version=aur_pkg.version,
                description=aur_pkg.desc,
                package=aur_pkg,
            ))

    def manual_package_selection(self):
        pkg_names_before = set(
            [
                update.name for update in (
                    self.repo_packages_install_info +
                    self.thirdparty_repo_packages_install_info +
                    self.aur_updates_install_info
                )
            ] + self.install_package_names + self.not_found_repo_pkgs_names
        )
        editor_cmd = self.get_editor()
        if not editor_cmd:
            return
        text = pretty_format_sysupgrade(
            self.repo_packages_install_info,
            self.thirdparty_repo_packages_install_info,
            self.aur_updates_install_info,
            color=False
        )
        selected_packages = []
        with NamedTemporaryFile() as tmp_file:
            with open_file(tmp_file.name, 'w') as write_file:
                write_file.write(text)
            interactive_spawn(
                editor_cmd + [tmp_file.name, ]
            )
            with open_file(tmp_file.name, 'r') as read_file:
                for line in read_file.readlines():
                    line = line.lstrip()
                    if not line:
                        continue
                    if not line.startswith('::') and not line.startswith('#'):
                        pkg_name = line.split()[0]
                        # for provided package selection: (mb later for optional deps)
                        pkg_name = pkg_name.split('#')[0].strip()
                        selected_packages.append(pkg_name)

        list_diff = set(selected_packages).difference(pkg_names_before)
        list_diff.update(selected_packages)
        for pkg_name in list_diff:
            if strip_aur_repo_name(pkg_name) not in (
                    self.install_package_names + self.not_found_repo_pkgs_names
            ):
                self.install_package_names.append(pkg_name)

        for pkg_name in pkg_names_before.difference(
                set([strip_aur_repo_name(p) for p in selected_packages])
        ):
            self.manually_excluded_packages_names.append(pkg_name)
            if pkg_name in self.install_package_names:
                self.install_package_names.remove(pkg_name)
            if pkg_name in self.not_found_repo_pkgs_names:
                self.not_found_repo_pkgs_names.remove(pkg_name)

    def install_prompt(self) -> None:

        def _print_sysupgrade(verbose=False) -> None:
            print_stdout(pretty_format_sysupgrade(
                repo_packages_updates=self.repo_packages_install_info,
                new_repo_deps=self.new_repo_deps_install_info,
                thirdparty_repo_packages_updates=self.thirdparty_repo_packages_install_info,
                new_thirdparty_repo_deps=None,
                aur_updates=self.aur_updates_install_info,
                new_aur_deps=self.aur_deps_install_info,
                verbose=verbose
            ))

        def _confirm_sysupgrade(verbose=False) -> str:
            _print_sysupgrade(verbose=verbose)
            prompt = '{} {}\n{} {}\n>> '.format(
                color_line('::', 12),
                bold_line(_('Proceed with installation? [Y/n] ')),
                color_line('::', 12),
                bold_line(_('[v]iew package detail   [m]anually select packages')))

            answer = get_input(prompt, _('y').upper() + _('n') + _('v') + _('m'))

            return answer

        if self.args.noconfirm:
            _print_sysupgrade()
            return
        answer = None
        while True:
            if answer is None:
                answer = _confirm_sysupgrade()
            if answer:
                letter = answer.lower()[0]
                if letter == _("y"):
                    break
                elif letter == _("v"):
                    answer = _confirm_sysupgrade(verbose=True)
                elif letter == _("m"):
                    print_stdout()
                    self.manual_package_selection()
                    self.get_all_packages_info()
                    self.install_prompt()
                    break
                else:
                    raise SysExit(125)
            else:
                break

    def discard_aur_package(
            self, canceled_pkg_name: str, already_discarded: List[str] = None
    ) -> None:
        if canceled_pkg_name in self.install_package_names:
            self.install_package_names.remove(canceled_pkg_name)
        already_discarded = (already_discarded or []) + [canceled_pkg_name]
        packages_to_be_removed = []
        for aur_pkg_name, aur_deps in list(self.aur_deps_relations.items())[:]:
            if canceled_pkg_name in aur_deps + [aur_pkg_name]:
                for pkg_name in aur_deps + [aur_pkg_name]:
                    if pkg_name not in already_discarded:
                        self.discard_aur_package(pkg_name, already_discarded)
                    pkg_build = self.package_builds_by_name.get(pkg_name)
                    if pkg_build and pkg_build.built_packages_installed and \
                       pkg_build.built_packages_installed.get(pkg_name):
                        packages_to_be_removed.append(pkg_name)
                        del pkg_build.built_packages_installed[pkg_name]
                if aur_pkg_name in self.aur_deps_relations:
                    del self.aur_deps_relations[aur_pkg_name]
        if packages_to_be_removed:
            self._remove_packages(list(set(packages_to_be_removed)))
        for pkg_name in already_discarded:
            if pkg_name in list(self.package_builds_by_name.keys()):
                del self.package_builds_by_name[pkg_name]

    def get_package_builds(self) -> None:
        if not self.all_aur_packages_names:
            return
        while self.all_aur_packages_names:
            try:
                self.package_builds_by_name = \
                    clone_aur_repos(self.all_aur_packages_names)
                break
            except CloneError as err:
                package_build = err.build
                print_stderr(color_line(
                    (
                        _("Can't clone '{name}' in '{path}' from AUR:")
                        if package_build.clone else
                        _("Can't pull '{name}' in '{path}' from AUR:")
                    ).format(
                        name=', '.join(package_build.package_names),
                        path=package_build.repo_path
                    ),
                    9
                ))
                print_stderr(err.result.stdout_text)
                print_stderr(err.result.stderr_text)
                if self.args.noconfirm:
                    answer = _("a")
                else:
                    prompt = '{} {}\n{}\n{}\n{}\n{}\n> '.format(
                        color_line('::', 11),
                        _("Try recovering?"),
                        _("[c] git checkout -- '*'"),
                        # _("[c] git checkout -- '*' ; git clean -f -d -x"),
                        _("[r] remove dir and clone again"),
                        _("[s] skip this package"),
                        _("[a] abort"))

                    answer = get_input(prompt, _('c') + _('r') + _('s') + _('a').upper())

                answer = answer.lower()[0]
                if answer == _("c"):
                    package_build.git_reset_changed()
                elif answer == _("r"):
                    remove_dir(package_build.repo_path)
                elif answer == _("s"):
                    for skip_pkg_name in package_build.package_names:
                        self.discard_aur_package(skip_pkg_name)
                else:
                    sys.exit(125)

    def ask_to_continue(self, text: str = None, default_yes=True) -> bool:
        return ask_to_continue(text=text, default_yes=default_yes, args=self.args)

    def ask_about_package_conflicts(self) -> None:
        if self.aur_packages_names:
            print_stdout(_('looking for conflicting AUR packages...'))
            self.found_conflicts.update(find_aur_conflicts(self.aur_packages_names))
        if not self.found_conflicts:
            return
        all_new_packages_names = list(self.repo_packages_by_name.keys()) + self.aur_packages_names
        for new_pkg_name, new_pkg_conflicts in self.found_conflicts.items():
            for pkg_conflict in new_pkg_conflicts:
                if pkg_conflict in all_new_packages_names:
                    print_stderr(color_line(
                        _("New packages '{new}' and '{other}' are in conflict.").format(
                            new=new_pkg_name, other=pkg_conflict),
                        9))
                    sys.exit(131)
        for new_pkg_name, new_pkg_conflicts in self.found_conflicts.items():
            for pkg_conflict in new_pkg_conflicts:
                answer = self.ask_to_continue('{} {}'.format(
                    color_line('::', 11),
                    bold_line(_(
                        "{new} and {installed} are in conflict. Remove {installed}?"
                    ).format(
                        new=new_pkg_name, installed=pkg_conflict
                    ))
                ), default_yes=False)
                if not answer:
                    sys.exit(125)
                self.resolved_conflicts.append([new_pkg_name, pkg_conflict])

    def ask_to_edit_file(self, filename: str, package_build: PackageBuild) -> bool:
        editor_cmd = self.get_editor()
        if not editor_cmd:
            return False
        noedit = not self.args.edit and (
            self.args.noedit or PikaurConfig().build.get_bool('NoEdit')
        )
        if noedit or self.args.noconfirm:
            print_stderr('{} {}'.format(
                color_line('::', 11),
                _("Skipping review of {file} for {name} package ({flag})").format(
                    file=filename,
                    name=', '.join(package_build.package_names),
                    flag=(noedit and '--noedit') or
                    (self.args.noconfirm and '--noconfirm')),
            ))
            return False
        if self.ask_to_continue(
                _("Do you want to {edit} {file} for {name} package?").format(
                    edit=bold_line(_("edit")),
                    file=filename,
                    name=bold_line(', '.join(package_build.package_names)),
                ),
                default_yes=not package_build.is_installed
        ):
            full_filename = os.path.join(
                package_build.repo_path,
                filename
            )
            old_hash = hash_file(full_filename)
            interactive_spawn(
                editor_cmd + [full_filename]
            )
            new_hash = hash_file(full_filename)
            return old_hash != new_hash
        return False

    def _preload_latest_sources(self) -> None:
        with ThreadPool() as pool:
            threads = []
            for repo_status in set(self.package_builds_by_name.values()):
                threads.append(
                    pool.apply_async(getattr, (repo_status, 'version_already_installed'))
                )
            pool.close()
            for thread in threads:
                thread.get()

    def review_build_files(self) -> None:
        if self.args.needed or self.args.devel:
            self._preload_latest_sources()
        for repo_status in set(self.package_builds_by_name.values()):
            if repo_status.reviewed:
                continue
            if self.args.needed and repo_status.version_already_installed:
                for package_name in repo_status.package_names:
                    print_package_uptodate(package_name, PackageSource.AUR)
                    self.discard_aur_package(package_name)
                continue
            if (
                    repo_status.build_files_updated
            ) and (
                repo_status.last_installed_hash
            ) and (
                not self.args.noconfirm
            ):
                nodiff = self.args.nodiff or PikaurConfig().build.get_bool('NoDiff')
                if not nodiff and self.ask_to_continue(
                        _("Do you want to see build files {diff} for {name} package?").format(
                            diff=bold_line(_("diff")),
                            name=bold_line(', '.join(repo_status.package_names))
                        )
                ):
                    interactive_spawn([
                        'git',
                        '-C',
                        repo_status.repo_path,
                        'diff',
                        repo_status.last_installed_hash,
                        repo_status.current_hash,
                    ])
            src_info = SrcInfo(repo_status.repo_path)

            if self.ask_to_edit_file('PKGBUILD', repo_status):
                src_info.regenerate()
                # @TODO: recompute AUR deps
                for pkg_name in repo_status.package_names:
                    install_src_info = SrcInfo(repo_status.repo_path, pkg_name)
                    install_file_name = install_src_info.get_install_script()
                    if install_file_name:
                        self.ask_to_edit_file(install_file_name, repo_status)

            _check_pkg_arch(repo_status)

    def build_packages(self) -> None:
        failed_to_build_package_names = []
        deps_fails_counter: Dict[str, int] = {}
        packages_to_be_built = self.all_aur_packages_names[:]
        index = 0
        while packages_to_be_built:
            if index >= len(packages_to_be_built):
                index = 0

            pkg_name = packages_to_be_built[index]
            repo_status = self.package_builds_by_name[pkg_name]
            if self.args.needed and repo_status.version_already_installed:
                print_package_uptodate(pkg_name, PackageSource.AUR)
                self.discard_aur_package(pkg_name)
                packages_to_be_built.remove(pkg_name)
                continue

            try:
                repo_status.build(self.package_builds_by_name)
            except (BuildError, DependencyError) as exc:
                print_stderr(exc)
                print_stderr(
                    color_line(_("Can't build '{name}'.").format(name=pkg_name) + '\n', 9)
                )
                # if not self.ask_to_continue():
                #     sys.exit(125)
                for _pkg_name in repo_status.package_names:
                    failed_to_build_package_names.append(_pkg_name)
                    self.discard_aur_package(_pkg_name)
                    for remaining_aur_pkg_name in packages_to_be_built[:]:
                        if remaining_aur_pkg_name not in self.all_aur_packages_names:
                            packages_to_be_built.remove(remaining_aur_pkg_name)
            except DependencyNotBuiltYet:
                index += 1
                for _pkg_name in repo_status.package_names:
                    deps_fails_counter.setdefault(_pkg_name, 0)
                    deps_fails_counter[_pkg_name] += 1
                    if deps_fails_counter[_pkg_name] > len(self.all_aur_packages_names):
                        print_stderr('{} {}'.format(
                            color_line(":: " + _("error:"), 9),
                            _("Dependency cycle detected between {}").format(deps_fails_counter)
                        ))
                        sys.exit(131)
            else:
                for _pkg_name in repo_status.package_names:
                    packages_to_be_built.remove(_pkg_name)

        self.failed_to_build_package_names = failed_to_build_package_names

    def _remove_packages(self, packages_to_be_removed: List[str]) -> None:
        # pylint: disable=no-self-use
        if packages_to_be_removed:
            retry_interactive_command_or_exit(
                sudo(
                    get_pacman_command(self.args) + [
                        '-Rs',
                    ] + packages_to_be_removed
                ),
                args=self.args,
                pikspect=True,
            )
            PackageDB.discard_local_cache()

    def _save_transaction(
            self,
            target: PackageSource,
            removed: List[str] = None,
            installed: List[str] = None
    ) -> None:
        target_transaction = self.transactions.setdefault(str(target), {})
        if removed:
            for pkg_name in removed:
                target_transaction.setdefault('removed', []).append(pkg_name)
        if installed:
            for pkg_name in installed:
                target_transaction.setdefault('installed', []).append(pkg_name)

    def save_repo_transaction(self, removed: List[str] = None, installed: List[str] = None) -> None:
        self._save_transaction(
            PackageSource.REPO, removed=removed, installed=installed
        )

    def save_aur_transaction(self, removed: List[str] = None, installed: List[str] = None) -> None:
        self._save_transaction(
            PackageSource.AUR, removed=removed, installed=installed
        )

    def _revert_transaction(self, target: PackageSource) -> None:
        if not self.transactions:
            return
        target_transaction = self.transactions.get(str(target))
        if not target_transaction:
            return
        print_stderr('{} {}'.format(
            color_line(':: warning', 9),
            _("Reverting {target} transaction...").format(target=target)
        ))
        removed = target_transaction.get('removed')
        installed = target_transaction.get('installed')
        if removed:
            pass  # install back
        if installed:
            self._remove_packages(installed)

    def revert_repo_transaction(self) -> None:
        self._revert_transaction(PackageSource.REPO)

    def revert_aur_transaction(self) -> None:
        self._revert_transaction(PackageSource.AUR)

    def install_repo_packages(self) -> None:
        print_stdout()
        extra_args = []
        if not (self.install_package_names or self.args.sysupgrade):
            return
        for excluded_pkg_name in self.manually_excluded_packages_names + (self.args.ignore or []):
            extra_args.append('--ignore')
            extra_args.append(excluded_pkg_name)
        if not retry_interactive_command(
                sudo(
                    get_pacman_command(self.args) + [
                        '--sync',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'sync',
                        'refresh',
                        'ignore',
                    ]) + self.install_package_names + extra_args
                ),
                args=self.args,
                pikspect=True,
                conflicts=self.resolved_conflicts,
        ):
            if not self.ask_to_continue(default_yes=False):
                self.revert_repo_transaction()
                sys.exit(125)
        PackageDB.discard_local_cache()
        self.save_repo_transaction(self.install_package_names)

    def install_new_aur_deps(self) -> None:
        new_aur_deps_to_install = [
            self.package_builds_by_name[pkg_name].built_packages_paths[pkg_name]
            for pkg_name in self.aur_deps_names
            if self.package_builds_by_name[pkg_name].built_packages_paths.get(pkg_name) and
            not self.package_builds_by_name[pkg_name].built_packages_installed.get(pkg_name)
        ]
        if new_aur_deps_to_install:
            if not retry_interactive_command(
                    sudo(
                        get_pacman_command(self.args) + [
                            '--upgrade',
                            '--asdeps',
                        ] + reconstruct_args(self.args, ignore_args=[
                            'upgrade',
                            'asdeps',
                            'sync',
                            'sysupgrade',
                            'refresh',
                            'ignore',
                        ]) + new_aur_deps_to_install
                    ),
                    args=self.args,
                    pikspect=True,
                    conflicts=self.resolved_conflicts,
            ):
                if not self.ask_to_continue(default_yes=False):
                    self.revert_aur_transaction()
                    sys.exit(125)
            PackageDB.discard_local_cache()
            self.save_aur_transaction(new_aur_deps_to_install)

    def install_aur_packages(self) -> None:
        aur_packages_to_install = [
            self.package_builds_by_name[pkg_name].built_packages_paths[pkg_name]
            for pkg_name in self.aur_packages_names
            if self.package_builds_by_name[pkg_name].built_packages_paths.get(pkg_name) and
            not self.package_builds_by_name[pkg_name].built_packages_installed.get(pkg_name)
        ]
        if aur_packages_to_install:
            if not retry_interactive_command(
                    sudo(
                        get_pacman_command(self.args) + [
                            '--upgrade',
                        ] + reconstruct_args(self.args, ignore_args=[
                            'upgrade',
                            'sync',
                            'sysupgrade',
                            'refresh',
                            'ignore',
                        ]) + aur_packages_to_install
                    ),
                    args=self.args,
                    pikspect=True,
                    conflicts=self.resolved_conflicts,
            ):
                if not self.ask_to_continue(default_yes=False):
                    self.revert_aur_transaction()
                    sys.exit(125)
            PackageDB.discard_local_cache()
            self.save_aur_transaction(aur_packages_to_install)

    def install_packages(self):

        # get sudo for further questions (command should do nothing):
        interactive_spawn(sudo([PikaurConfig().misc.PacmanPath, '-T']))

        if not self.args.aur:
            self.install_repo_packages()

        self.build_packages()
        if not self.args.downloadonly:
            self.install_new_aur_deps()
            self.install_aur_packages()

        # save git hash of last sucessfully installed package
        if self.package_builds_by_name:
            package_builds_by_base = {
                pkgbuild.package_base: pkgbuild
                for pkgbuild in self.package_builds_by_name.values()
            }
            for package_build in package_builds_by_base.values():
                if len(package_build.built_packages_paths) == len(package_build.package_names):
                    if not self.args.downloadonly:
                        package_build.update_last_installed_file()
                    if not (self.args.keepbuild or PikaurConfig().build.get_bool('KeepBuildDir')):
                        remove_dir(package_build.build_dir)

        if self.failed_to_build_package_names:
            print_stderr('\n'.join(
                [color_line(_("Failed to build following packages:"), 9), ] +
                self.failed_to_build_package_names
            ))
            sys.exit(1)
