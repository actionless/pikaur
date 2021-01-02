""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=too-many-lines
import os
import hashlib
from multiprocessing.pool import ThreadPool
from tempfile import NamedTemporaryFile
from typing import List, Dict, Optional, Set, Any

import pyalpm

from .i18n import _
from .config import PikaurConfig
from .args import reconstruct_args, PikaurArgs, parse_args
from .aur import AURPackageInfo
from .pacman import (
    PackageDB,
    get_pacman_command, refresh_pkg_db, install_built_deps, strip_repo_name,
)
from .install_info_fetcher import InstallInfoFetcher
from .exceptions import (
    SysExit, PackagesNotFoundInAUR, DependencyVersionMismatch,
    BuildError, CloneError, DependencyError, DependencyNotBuiltYet,
)
from .build import PackageBuild, clone_aur_repos, PkgbuildChanged
from .pprint import (
    color_line, bold_line,
    print_stderr, print_stdout, print_warning, print_error, print_debug,
)
from .print_department import (
    pretty_format_sysupgrade,
    print_not_found_packages, print_package_uptodate,
    print_package_downgrading, print_local_package_newer,
)
from .core import (
    PackageSource,
    interactive_spawn, remove_dir, open_file, sudo, running_as_root,
)
from .conflicts import find_aur_conflicts
from .prompt import (
    ask_to_continue, retry_interactive_command,
    retry_interactive_command_or_exit, get_input, get_editor_or_exit
)
from .srcinfo import SrcInfo
from .news import News
from .version import compare_versions
from .updates import is_devel_pkg


def debug(msg: Any) -> None:
    print_debug(f"install_cli: {str(msg)}")


def hash_file(filename: str) -> str:  # pragma: no cover
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


def edit_file(filename: str) -> bool:  # pragma: no cover
    editor_cmd = get_editor_or_exit()
    if not editor_cmd:
        return False
    old_hash = hash_file(filename)
    interactive_spawn(
        editor_cmd + [filename]
    )
    new_hash = hash_file(filename)
    return old_hash != new_hash


class InstallPackagesCLI():

    # User input
    args: PikaurArgs
    install_package_names: List[str]
    manually_excluded_packages_names: List[str]
    resolved_conflicts: List[List[str]]
    # pkgbuild_path: [pkg_name, ...]  -- needed for split pkgs to install only some of them
    pkgbuilds_packagelists: Dict[str, List[str]]

    # computed package lists:
    not_found_repo_pkgs_names: List[str]
    found_conflicts: Dict[str, List[str]]
    repo_packages_by_name: Dict[str, pyalpm.Package]
    # pkgbuilds from cloned aur repos:
    package_builds_by_name: Dict[str, PackageBuild]

    # Packages' install info
    install_info: InstallInfoFetcher

    # Installation results
    # transactions by PackageSource(AUR/repo), direction(removed/installed):
    transactions: Dict[str, Dict[str, List[str]]]
    # AUR packages which failed to build:
    # @TODO: refactor to store in transactions
    failed_to_build_package_names: List[str]

    # arch news
    news: Optional[News] = None

    def __init__(self) -> None:
        self.args = parse_args()
        self.install_package_names = self.args.positional[:]

        self.pkgbuilds_packagelists = {}
        self.manually_excluded_packages_names = []
        self.resolved_conflicts = []

        self.not_found_repo_pkgs_names = []
        self.repo_packages_by_name = {}
        self.package_builds_by_name = {}

        self.found_conflicts = {}
        self.transactions = {}
        self.failed_to_build_package_names = []

        if not self.args.aur and (self.args.sysupgrade or self.args.refresh):

            with ThreadPool() as pool:
                threads = []
                if self.args.sysupgrade:
                    self.news = News()
                    threads.append(
                        pool.apply_async(self.news.fetch_latest, ())
                    )
                if self.args.refresh:
                    threads.append(
                        pool.apply_async(refresh_pkg_db, ())
                    )
                pool.close()
                for thread in threads:
                    thread.get()
                pool.join()

            if not (self.install_package_names or self.args.sysupgrade):
                return

            if self.args.refresh:
                PackageDB.discard_repo_cache()
                print_stdout()

        if self.args.sysupgrade and not self.args.repo:
            print_stderr('{} {}'.format(
                color_line('::', 12),
                bold_line(_("Starting full AUR upgrade..."))
            ))
        if self.args.aur:
            self.not_found_repo_pkgs_names = self.install_package_names
            self.install_package_names = []
        if self.args.pkgbuild:
            self.get_info_from_pkgbuilds()

        self.main_sequence()

    class ExitMainSequence(Exception):
        pass

    def main_sequence(self):
        try:
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
        except self.ExitMainSequence:
            pass

    @property
    def aur_packages_names(self) -> List[str]:
        return self.install_info.aur_packages_names

    @property
    def aur_deps_names(self) -> List[str]:
        return self.install_info.aur_deps_names

    @property
    def all_aur_packages_names(self) -> List[str]:
        return list(set(self.aur_packages_names + self.aur_deps_names))

    def get_info_from_pkgbuilds(self) -> None:
        self.install_package_names = []
        self.not_found_repo_pkgs_names = []
        self.pkgbuilds_packagelists = {
            path: [] for path in
            self.args.positional or ['PKGBUILD']
        }

    def aur_pkg_not_found_prompt(self, pkg_name: str) -> None:  # pragma: no cover
        prompt = '{} {}\n{}\n{}\n{}\n> '.format(
            color_line('::', 11),
            _("Try recovering?"),
            _("[e] edit PKGBUILD"),
            _("[s] skip this package"),
            _("[A] abort")
        )
        answer = get_input(prompt, _('e') + _('s') + _('a').upper())

        answer = answer.lower()[0]
        if answer == _("e"):
            updated_pkgbuilds = self._clone_aur_repos([pkg_name])
            if not updated_pkgbuilds:
                return
            self.package_builds_by_name.update(updated_pkgbuilds)
            pkg_build = self.package_builds_by_name[pkg_name]
            if not edit_file(
                    pkg_build.pkgbuild_path
            ):
                print_warning(_("PKGBUILD appears unchanged after editing"))
            else:
                self.handle_pkgbuild_changed(pkg_build)
            self._ignore_package(pkg_name)
            self.pkgbuilds_packagelists[pkg_build.pkgbuild_path] = pkg_build.package_names
            self.main_sequence()
        elif answer == _("s"):
            self._ignore_package(pkg_name)
        else:
            raise SysExit(125)

    def get_all_packages_info(self) -> None:  # pylint:disable=too-many-branches
        """
        Retrieve info (`InstallInfo` objects) of packages
        which are going to be installed/upgraded and their dependencies
        """

        # deal with package names which user explicitly wants to install
        self.repo_packages_by_name = {}

        for pkg_name in self.manually_excluded_packages_names:
            if pkg_name in self.install_package_names:
                self.install_package_names.remove(pkg_name)

        try:
            self.install_info = InstallInfoFetcher(
                install_package_names=self.install_package_names,
                not_found_repo_pkgs_names=self.not_found_repo_pkgs_names,
                pkgbuilds_packagelists=self.pkgbuilds_packagelists,
                manually_excluded_packages_names=self.manually_excluded_packages_names,
            )
        except PackagesNotFoundInAUR as exc:
            if exc.wanted_by:
                print_error(bold_line(
                    _("Dependencies missing for {}").format(', '.join(exc.wanted_by))
                ))
                print_not_found_packages(exc.packages)
                for pkg_name in exc.wanted_by:  # pylint: disable=not-an-iterable
                    self.aur_pkg_not_found_prompt(pkg_name)
                self.get_all_packages_info()
                return
            print_not_found_packages(exc.packages)
            raise SysExit(131) from exc
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
            raise SysExit(131) from exc

        if self.args.repo and self.not_found_repo_pkgs_names:
            print_not_found_packages(self.not_found_repo_pkgs_names, repo=True)
            raise SysExit(6)

        if self.args.needed:
            # check if there are really any new packages need to be installed
            need_refetch_info = False
            for install_info in (
                    self.install_info.repo_packages_install_info +
                    self.install_info.new_repo_deps_install_info +
                    self.install_info.thirdparty_repo_packages_install_info +
                    self.install_info.aur_updates_install_info
            ):
                if (
                        # devel packages will be checked later
                        # after retrieving their sources
                        is_devel_pkg(install_info.name) and
                        (install_info in self.install_info.aur_updates_install_info)
                ) or (
                    not install_info.current_version
                ) or compare_versions(
                    install_info.current_version,
                    install_info.new_version
                ) or (
                    # package installed via Provides, not by its real name
                    install_info.name not in self.install_package_names
                ):
                    continue
                print_package_uptodate(install_info.name, install_info.package_source)
                self.discard_install_info(install_info.name)
                need_refetch_info = True
            if need_refetch_info:
                self.get_all_packages_info()
                return

        # check if we really need to build/install anything
        if not (
                self.install_info.repo_packages_install_info or
                self.install_info.new_repo_deps_install_info or
                self.install_info.thirdparty_repo_packages_install_info or
                self.install_info.aur_updates_install_info
        ):
            if not self.args.aur and self.args.sysupgrade:
                self.install_repo_packages()
            else:
                print_stdout('{} {}'.format(
                    color_line('::', 10),
                    _("Nothing to do."),
                ))
            raise SysExit(0)

    def _ignore_package(self, pkg_name: str) -> None:
        self.manually_excluded_packages_names.append(pkg_name)
        for name in (pkg_name, strip_repo_name(pkg_name), ):
            if name in self.install_package_names:
                self.install_package_names.remove(name)
            if name in self.not_found_repo_pkgs_names:
                self.not_found_repo_pkgs_names.remove(name)

    def manual_package_selection(self) -> None:  # pragma: no cover
        editor_cmd = get_editor_or_exit()
        if not editor_cmd:
            return

        def parse_pkg_names(text: str) -> Set[str]:
            selected_packages = []
            for line in text.splitlines():
                line = line.lstrip()
                if not line:
                    continue
                if not line.startswith('::') and not line.startswith('#'):
                    pkg_name = line.split()[0]
                    # for provided package selection: (mb later for optional deps)
                    pkg_name = pkg_name.split('#')[0].strip()
                    selected_packages.append(pkg_name)
            return set(selected_packages)

        text_before = pretty_format_sysupgrade(
            install_info=self.install_info,
            manual_package_selection=True
        )
        pkg_names_before = parse_pkg_names(text_before)
        with NamedTemporaryFile() as tmp_file:
            with open_file(tmp_file.name, 'w') as write_file:
                write_file.write(text_before)
            interactive_spawn(
                editor_cmd + [tmp_file.name, ]
            )
            with open_file(tmp_file.name, 'r') as read_file:
                selected_packages = parse_pkg_names(read_file.read())

        list_diff = selected_packages.difference(pkg_names_before)
        for pkg_name in list_diff:
            if pkg_name not in (
                    self.install_package_names + self.not_found_repo_pkgs_names
            ):
                self.install_package_names.append(pkg_name)

        for pkg_name in pkg_names_before.difference(selected_packages):
            self._ignore_package(pkg_name)

    def install_prompt(self) -> None:  # pragma: no cover

        def _print_sysupgrade(verbose=False) -> None:
            print_stdout(pretty_format_sysupgrade(
                install_info=self.install_info,
                verbose=verbose
            ))

        def _confirm_sysupgrade(verbose=False) -> str:
            _print_sysupgrade(verbose=verbose)
            prompt = '{} {}\n{} {}\n>> '.format(
                color_line('::', 12),
                bold_line(_('Proceed with installation? [Y/n] ')),
                color_line('::', 12),
                bold_line(_('[v]iew package details   [m]anually select packages')))

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
                if letter == _("v"):
                    answer = _confirm_sysupgrade(verbose=True)
                    continue
                if letter == _("m"):
                    print_stdout()
                    self.manual_package_selection()
                    self.get_all_packages_info()
                    self.install_prompt()
                    break
                raise SysExit(125)
            break

    def discard_install_info(self, canceled_pkg_name: str) -> None:
        debug(f"discarding install info for pkg... {canceled_pkg_name}")
        self.manually_excluded_packages_names.append(canceled_pkg_name)
        if not getattr(self, 'install_info', None):  # @TODO: make it nicer?
            debug("install info not initialized yet -- running on early stage?")
            return
        for pkg_name in self.install_info.discard_package(canceled_pkg_name):
            debug(f"discarded install info for pkg: {pkg_name}")
            if pkg_name in self.install_package_names:
                self.install_package_names.remove(pkg_name)
            if pkg_name in self.not_found_repo_pkgs_names:
                self.not_found_repo_pkgs_names.remove(pkg_name)
            if pkg_name in list(self.package_builds_by_name.keys()):
                del self.package_builds_by_name[pkg_name]

    def _find_extra_aur_build_deps(self, all_package_builds: Dict[str, PackageBuild]):
        need_to_show_install_prompt = False
        for pkgbuild in all_package_builds.values():
            pkgbuild.get_deps(all_package_builds=all_package_builds, filter_built=False)

            aur_pkgs: List[AURPackageInfo] = [
                info.package  # type: ignore[misc]
                for container in self.install_info.all_install_info
                for info in container
                if info.name in pkgbuild.package_names
            ]
            aur_rpc_deps = set(
                dep_line
                for pkg in aur_pkgs
                for dep_line in (
                    pkg.depends +
                    pkg.makedepends +
                    pkg.checkdepends
                )
            )

            srcinfo_deps: Set[str] = set()
            for package_name in pkgbuild.package_names:
                src_info = SrcInfo(pkgbuild_path=pkgbuild.pkgbuild_path, package_name=package_name)
                srcinfo_deps.update(set(
                    dep_line
                    for matcher in
                    list(src_info.get_depends().values()) +
                    list(src_info.get_build_makedepends().values()) +
                    list(src_info.get_build_checkdepends().values())
                    for dep_line in matcher.line.split(',')
                ))

            if aur_rpc_deps != srcinfo_deps:
                deps_added = srcinfo_deps.difference(aur_rpc_deps)
                deps_removed = aur_rpc_deps.difference(srcinfo_deps)
                if deps_added:
                    print_warning(_("New build deps found for {pkg} package: {deps}").format(
                        pkg=bold_line(', '.join(pkgbuild.package_names)),
                        deps=bold_line(', '.join(deps_added)),
                    ))
                if deps_removed:
                    print_warning(_("Some build deps removed for {pkg} package: {deps}").format(
                        pkg=bold_line(', '.join(pkgbuild.package_names)),
                        deps=bold_line(', '.join(deps_removed)),
                    ))
                for pkg_name in pkgbuild.package_names:
                    self.discard_install_info(pkg_name)
                self.pkgbuilds_packagelists[pkgbuild.pkgbuild_path] = pkgbuild.package_names
                need_to_show_install_prompt = True
        if need_to_show_install_prompt:
            self.main_sequence()
            raise self.ExitMainSequence()

    def _clone_aur_repos(self, package_names: List[str]) -> Optional[Dict[str, PackageBuild]]:
        while True:
            try:
                return clone_aur_repos(package_names=package_names)
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
                else:  # pragma: no cover
                    prompt = '{} {}\n{}\n{}\n{}\n{}\n> '.format(
                        color_line('::', 11),
                        _("Try recovering?"),
                        _("[c] git checkout -- '*'"),
                        # _("[c] git checkout -- '*' ; git clean -f -d -x"),
                        _("[r] remove dir and clone again"),
                        _("[s] skip this package"),
                        _("[A] abort")
                    )
                    answer = get_input(prompt, _('c') + _('r') + _('s') + _('a').upper())

                answer = answer.lower()[0]
                if answer == _("c"):  # pragma: no cover
                    package_build.git_reset_changed()
                elif answer == _("r"):  # pragma: no cover
                    remove_dir(package_build.repo_path)
                elif answer == _("s"):  # pragma: no cover
                    for skip_pkg_name in package_build.package_names:
                        self.discard_install_info(skip_pkg_name)
                        if skip_pkg_name in package_names:
                            package_names.remove(skip_pkg_name)
                else:
                    raise SysExit(125) from err

    def get_package_builds(self) -> None:  # pylint: disable=too-many-branches
        while self.all_aur_packages_names:
            clone_names = []
            pkgbuilds_by_base: Dict[str, PackageBuild] = {}
            pkgbuilds_by_name = {}
            for info in (
                    self.install_info.aur_updates_install_info +
                    self.install_info.aur_deps_install_info
            ):
                if info.pkgbuild_path:
                    if not isinstance(info.package, AURPackageInfo):
                        raise TypeError()
                    pkg_base = info.package.packagebase
                    if pkg_base not in pkgbuilds_by_base:
                        package_names = self.pkgbuilds_packagelists.get(info.pkgbuild_path)
                        print_debug(
                            f"Initializing build info for {pkg_base=}, "
                            f"{info.pkgbuild_path=}, {package_names=}"
                        )
                        pkgbuilds_by_base[pkg_base] = PackageBuild(
                            pkgbuild_path=info.pkgbuild_path,
                            package_names=package_names
                        )
                    pkgbuilds_by_name[info.name] = pkgbuilds_by_base[pkg_base]
                else:
                    clone_names.append(info.name)
            cloned_pkgbuilds = self._clone_aur_repos(clone_names)
            if cloned_pkgbuilds:
                pkgbuilds_by_name.update(cloned_pkgbuilds)
            for pkg_list in (self.aur_packages_names, self.aur_deps_names):
                self._find_extra_aur_build_deps(
                    all_package_builds={
                        pkg_name: pkgbuild for pkg_name, pkgbuild
                        in pkgbuilds_by_name.items()
                        if pkg_name in pkg_list
                    }
                )
            self.package_builds_by_name = pkgbuilds_by_name
            break

    def ask_about_package_conflicts(self) -> None:
        if self.aur_packages_names or self.aur_deps_names:
            print_stderr(_('looking for conflicting AUR packages...'))
            self.found_conflicts.update(
                find_aur_conflicts(
                    self.aur_packages_names + self.aur_deps_names,
                    self.install_package_names
                )
            )
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
                    raise SysExit(131)
        for new_pkg_name, new_pkg_conflicts in self.found_conflicts.items():
            for pkg_conflict in new_pkg_conflicts:
                answer = ask_to_continue('{} {}'.format(
                    color_line('::', 11),
                    bold_line(_(
                        "{new} and {installed} are in conflict. Remove {installed}?"
                    ).format(
                        new=new_pkg_name, installed=pkg_conflict
                    ))
                ), default_yes=False)
                if not answer:
                    raise SysExit(131)
                self.resolved_conflicts.append([new_pkg_name, pkg_conflict])

    def ask_to_edit_file(
            self, filename: str, package_build: PackageBuild
    ) -> bool:  # pragma: no cover
        noedit = not self.args.edit and (
            self.args.noedit
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
        if not ask_to_continue(
                _("Do you want to {edit} {file} for {name} package?").format(
                    edit=bold_line(_("edit")),
                    file=filename,
                    name=bold_line(', '.join(package_build.package_names)),
                ),
                default_yes=not (package_build.last_installed_hash or
                                 PikaurConfig().review.DontEditByDefault.get_bool())
        ):
            return False
        full_filename = os.path.join(
            package_build.repo_path,
            filename
        )
        return edit_file(full_filename)

    def _get_installed_status(self) -> None:
        all_package_builds = set(self.package_builds_by_name.values())

        # if running as root get sources for dev packages synchronously
        # (to prevent race condition in systemd dynamic users)
        num_threads: Optional[int] = None
        if running_as_root():  # pragma: no cover
            num_threads = 1

        # check if pkgs versions already installed
        # (use threads because devel packages require downloading
        # latest sources for quite a long time)
        with ThreadPool(processes=num_threads) as pool:
            threads = []
            for pkg_build in all_package_builds:
                threads.append(
                    pool.apply_async(getattr, (pkg_build, 'version_already_installed'))
                )
            for thread in threads:
                thread.get()
            pool.close()
            pool.join()

        # handle if version is already installed
        if not self.args.needed:
            return
        local_db = PackageDB.get_local_dict()
        for pkg_build in all_package_builds:
            if not pkg_build.reviewed:
                continue
            # pragma: no cover
            pkg_build.update_last_installed_file()
            for package_name in pkg_build.package_names:
                if package_name not in local_db:
                    continue
                if pkg_build.version_already_installed:
                    print_package_uptodate(package_name, PackageSource.AUR)
                    self.discard_install_info(package_name)
                elif (
                        self.args.sysupgrade > 1
                ) or (
                    is_devel_pkg(pkg_build.package_base) and (self.args.devel > 1)
                ):
                    if not pkg_build.version_is_upgradeable:
                        print_package_downgrading(
                            package_name,
                            downgrade_version=pkg_build.get_version(package_name)
                        )
                elif not pkg_build.version_is_upgradeable:
                    print_local_package_newer(
                        package_name,
                        aur_version=pkg_build.get_version(package_name)
                    )
                    self.discard_install_info(package_name)

    def review_build_files(self) -> None:  # pragma: no cover  pylint:disable=too-many-branches
        if self.args.needed or self.args.devel:
            self._get_installed_status()
        for pkg_build in set(self.package_builds_by_name.values()):
            _pkg_label = bold_line(', '.join(pkg_build.package_names))
            _skip_diff_label = _("Not showing diff for {pkg} package ({reason})")

            if (
                    pkg_build.last_installed_hash != pkg_build.current_hash
            ) and (
                pkg_build.last_installed_hash
            ) and (
                pkg_build.current_hash
            ) and (
                not self.args.noconfirm
            ):
                if not self.args.nodiff and ask_to_continue(
                        _("Do you want to see build files {diff} for {name} package?").format(
                            diff=bold_line(_("diff")),
                            name=_pkg_label
                        )
                ):
                    git_args: List[str] = []
                    diff_pager = PikaurConfig().review.DiffPager
                    if diff_pager == 'always':
                        git_args = ['env', 'GIT_PAGER=less -+F']
                    elif diff_pager == 'never':
                        git_args = ['env', 'GIT_PAGER=cat']
                    git_args += [
                        'git',
                        '-C',
                        pkg_build.repo_path,
                        'diff',
                    ] + PikaurConfig().review.GitDiffArgs.get_str().split(',') + [
                        pkg_build.last_installed_hash,
                        pkg_build.current_hash,
                        '--', '.',
                    ]
                    for file_path in PikaurConfig().review.HideDiffFiles.get_str().split(','):
                        if file_path:
                            git_args += [
                                f':(exclude){file_path}',
                            ]
                    interactive_spawn(git_args)
            elif self.args.noconfirm:
                print_stdout(_skip_diff_label.format(
                    pkg=_pkg_label,
                    reason="--noconfirm"
                ))
            elif not pkg_build.last_installed_hash:
                print_warning(_skip_diff_label.format(
                    pkg=_pkg_label,
                    reason=_("installing for the first time")
                ))
            else:
                print_warning(_skip_diff_label.format(
                    pkg=_pkg_label,
                    reason=_("already reviewed")
                ))

            if self.ask_to_edit_file(
                    os.path.basename(pkg_build.pkgbuild_path), pkg_build
            ):
                self.handle_pkgbuild_changed(pkg_build)

            for pkg_name in pkg_build.package_names:
                install_src_info = SrcInfo(
                    pkgbuild_path=pkg_build.pkgbuild_path,
                    package_name=pkg_name
                )
                install_file_name = install_src_info.get_install_script()
                if install_file_name:
                    self.ask_to_edit_file(install_file_name, pkg_build)

            pkg_build.check_pkg_arch()
            pkg_build.reviewed = True

    def handle_pkgbuild_changed(self, pkg_build: PackageBuild) -> None:
        for pkg_name in pkg_build.package_names:
            self.discard_install_info(pkg_name)
        src_info = SrcInfo(pkgbuild_path=pkg_build.pkgbuild_path)
        old_srcinfo_hash = hash_file(src_info.path)
        src_info.regenerate()
        new_srcinfo_hash = hash_file(src_info.path)

        self.pkgbuilds_packagelists[pkg_build.pkgbuild_path] = pkg_build.package_names

        if not getattr(self, 'install_info', None):  # @TODO: make it nicer?
            debug("install info not initialized yet -- running on early stage?")
            if old_srcinfo_hash != new_srcinfo_hash:
                print_warning(_(
                    "Installation info changed (or new deps found) for {pkg} package"
                ).format(
                    pkg=bold_line(', '.join(pkg_build.package_names)),
                ))
                self.main_sequence()
                raise self.ExitMainSequence()
            return

        old_install_info = self.install_info
        self.get_all_packages_info()
        old_install_info.pkgbuilds_packagelists = self.install_info.pkgbuilds_packagelists
        if old_install_info != self.install_info or old_srcinfo_hash != new_srcinfo_hash:
            print_warning(_(
                "Installation info changed (or new deps found) for {pkg} package"
            ).format(
                pkg=bold_line(', '.join(pkg_build.package_names)),
            ))
            self.main_sequence()
            raise self.ExitMainSequence()

    def build_packages(self) -> None:  # pylint: disable=too-many-branches
        if self.args.needed or self.args.devel:
            self._get_installed_status()

        failed_to_build_package_names = []
        deps_fails_counter: Dict[str, int] = {}
        packages_to_be_built = self.all_aur_packages_names[:]
        index = 0
        while packages_to_be_built:
            print_debug(f"Gonna build {self.package_builds_by_name=}")
            if index >= len(packages_to_be_built):
                index = 0

            pkg_name = packages_to_be_built[index]
            pkg_build = self.package_builds_by_name[pkg_name]
            if self.args.needed and pkg_build.version_already_installed:
                packages_to_be_built.remove(pkg_name)
                continue

            try:
                print_debug(f"Gonna build {pkg_build.package_names=}")
                pkg_build.build(
                    all_package_builds=self.package_builds_by_name,
                    resolved_conflicts=self.resolved_conflicts
                )
            except PkgbuildChanged:
                self.handle_pkgbuild_changed(pkg_build)
            except (BuildError, DependencyError) as exc:
                print_stderr(exc)
                print_stderr(
                    color_line(_("Can't build '{name}'.").format(name=pkg_name) + '\n', 9)
                )
                # if not ask_to_continue():
                #     raise SysExit(125)
                for _pkg_name in pkg_build.package_names:
                    failed_to_build_package_names.append(_pkg_name)
                    packages_to_be_built.remove(_pkg_name)
                    self.discard_install_info(_pkg_name)
                    for remaining_aur_pkg_name in packages_to_be_built[:]:
                        if remaining_aur_pkg_name not in self.all_aur_packages_names:
                            packages_to_be_built.remove(remaining_aur_pkg_name)
            except DependencyNotBuiltYet as exc:
                index += 1
                for _pkg_name in pkg_build.package_names:
                    deps_fails_counter.setdefault(_pkg_name, 0)
                    deps_fails_counter[_pkg_name] += 1
                    if deps_fails_counter[_pkg_name] > len(self.all_aur_packages_names):
                        print_error(
                            _("Dependency cycle detected between {}").format(deps_fails_counter)
                        )
                        raise SysExit(131) from exc
            else:
                print_debug(
                    f"Build done for packages {pkg_build.package_names=}, removing from queue"
                )
                for _pkg_name in pkg_build.package_names:
                    packages_to_be_built.remove(_pkg_name)

        self.failed_to_build_package_names = failed_to_build_package_names

    def _remove_packages(self, packages_to_be_removed: List[str]) -> None:
        # pylint: disable=no-self-use
        if packages_to_be_removed:
            retry_interactive_command_or_exit(
                sudo(
                    get_pacman_command() + [
                        '-Rs',
                    ] + packages_to_be_removed
                ),
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

    def _revert_transaction(self, target: PackageSource) -> None:
        if not self.transactions:
            return
        target_transaction = self.transactions.get(str(target))
        if not target_transaction:
            return
        print_warning(
            _("Reverting {target} transaction...").format(target=target)
        )
        removed = target_transaction.get('removed')
        installed = target_transaction.get('installed')
        if removed:
            pass  # install back
        if installed:
            self._remove_packages(installed)

    def install_repo_packages(self) -> None:
        print_stdout()
        extra_args = []
        if not (self.install_package_names or self.args.sysupgrade):
            return
        for excluded_pkg_name in self.manually_excluded_packages_names + self.args.ignore:
            extra_args.append('--ignore')
            # pacman's --ignore doesn't work with repo name:
            extra_args.append(strip_repo_name(excluded_pkg_name))
        if not retry_interactive_command(
                sudo(
                    get_pacman_command() + [
                        '--sync',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'sync',
                        'ignore',
                        'refresh',
                    ]) + self.install_package_names + extra_args
                ),
                pikspect=True,
                conflicts=self.resolved_conflicts,
        ):
            if not ask_to_continue(default_yes=False):  # pragma: no cover
                self._revert_transaction(PackageSource.REPO)
                raise SysExit(125)
        PackageDB.discard_local_cache()
        self._save_transaction(
            PackageSource.REPO, installed=self.install_package_names
        )

    def install_new_aur_deps(self) -> None:
        new_aur_deps_to_install = {
            pkg_name: self.package_builds_by_name[pkg_name].built_packages_paths[pkg_name]
            for pkg_name in self.aur_deps_names
        }
        try:
            install_built_deps(
                deps_names_and_paths=new_aur_deps_to_install,
                resolved_conflicts=self.resolved_conflicts
            )
        except DependencyError as exc:
            if not ask_to_continue(default_yes=False):
                self._revert_transaction(PackageSource.AUR)
                raise SysExit(125) from exc
        else:
            self._save_transaction(
                PackageSource.AUR, installed=list(new_aur_deps_to_install.keys())
            )

    def install_aur_packages(self) -> None:
        aur_packages_to_install = {
            pkg_name: self.package_builds_by_name[pkg_name].built_packages_paths[pkg_name]
            for pkg_name in self.aur_packages_names
        }
        if aur_packages_to_install:
            if not retry_interactive_command(
                    sudo(
                        get_pacman_command() + [
                            '--upgrade',
                        ] + reconstruct_args(self.args, ignore_args=[
                            'upgrade',
                            'sync',
                            'sysupgrade',
                            'refresh',
                            'ignore',
                        ]) + list(aur_packages_to_install.values())
                    ),
                    pikspect=True,
                    conflicts=self.resolved_conflicts,
            ):
                if not ask_to_continue(default_yes=False):  # pragma: no cover
                    self._revert_transaction(PackageSource.AUR)
                    raise SysExit(125)
            PackageDB.discard_local_cache()
            self._save_transaction(
                PackageSource.AUR, installed=list(aur_packages_to_install.keys())
            )

    def install_packages(self) -> None:

        if not self.args.aur:
            self.install_repo_packages()

        self.build_packages()
        if (
                not self.args.downloadonly
        ) and (
            not self.args.pkgbuild or self.args.install
        ):
            self.install_new_aur_deps()
            self.install_aur_packages()

        # save git hash of last successfully installed package
        if self.package_builds_by_name:
            package_builds_by_base = {
                pkgbuild.package_base: pkgbuild
                for pkgbuild in self.package_builds_by_name.values()
            }
            for package_build in package_builds_by_base.values():
                if len(package_build.built_packages_paths) == len(package_build.package_names):
                    if not self.args.downloadonly:
                        package_build.update_last_installed_file()
                    if not package_build.keep_build_dir:
                        remove_dir(package_build.build_dir)

        if self.failed_to_build_package_names:
            print_stderr('\n'.join(
                [color_line(_("Failed to build following packages:"), 9), ] +
                self.failed_to_build_package_names
            ))
            raise SysExit(1)
