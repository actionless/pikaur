""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

# pylint: disable=too-many-lines
import os
import hashlib
from multiprocessing.pool import ThreadPool
from tempfile import NamedTemporaryFile
from typing import List, Dict, Optional

import pyalpm

from .i18n import _
from .config import PikaurConfig
from .args import reconstruct_args, PikaurArgs, parse_args
from .aur import strip_aur_repo_name
from .pacman import (
    PackageDB,
    get_pacman_command, refresh_pkg_db, install_built_deps,
)
from .install_info_fetcher import InstallInfoFetcher
from .exceptions import (
    PackagesNotFoundInAUR, DependencyVersionMismatch,
    BuildError, CloneError, DependencyError, DependencyNotBuiltYet,
    SysExit,
)
from .build import PackageBuild, clone_aur_repos
from .makepkg_config import MakepkgConfig
from .pprint import (
    color_line, bold_line,
    print_stderr, print_stdout, print_warning, print_error,
)
from .print_department import (
    pretty_format_sysupgrade, print_not_found_packages, print_package_uptodate,
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
from .srcinfo import SrcInfo
from .news import News


def check_pkg_arch(pkgbuild):
    src_info = SrcInfo(pkgbuild_path=pkgbuild.pkgbuild_path)
    arch = MakepkgConfig.get('CARCH')
    supported_archs = src_info.get_values('arch')
    if supported_archs and (
            'any' not in supported_archs
    ) and (
        arch not in supported_archs
    ):
        print_error(
            _("{name} can't be built on the current arch ({arch}). "
              "Supported: {suparch}").format(
                  name=bold_line(', '.join(pkgbuild.package_names)),
                  arch=arch,
                  suparch=', '.join(supported_archs))
        )
        raise SysExit(95)


def hash_file(filename):  # pragma: no cover
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


def get_editor_or_exit() -> Optional[List[str]]:
    editor = get_editor()
    if not editor:
        print_warning(_("no editor found. Try setting $VISUAL or $EDITOR."))
        if not ask_to_continue(_("Do you want to proceed without editing?")):  # pragma: no cover
            raise SysExit(125)
    return editor


class InstallPackagesCLI():

    # User input
    args: PikaurArgs
    install_package_names: List[str]
    manually_excluded_packages_names: List[str]
    resolved_conflicts: List[List[str]]
    pkgbuilds_paths: List[str]

    # computed package lists:
    not_found_repo_pkgs_names: List[str]
    found_conflicts: Dict[str, List[str]]
    repo_packages_by_name: Dict[str, pyalpm.Package]
    aur_deps_relations: Dict[str, List[str]]
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

        self.pkgbuilds_paths = []
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
            if self.args.sysupgrade:
                self.news = News()
            with ThreadPool() as pool:
                pool.apply_async(refresh_pkg_db, ())
                if self.news:
                    pool.apply_async(self.news.fetch_latest, ())
                pool.close()
                pool.join()
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

    def get_info_from_pkgbuilds(self):
        self.install_package_names = []
        self.not_found_repo_pkgs_names = []
        self.pkgbuilds_paths = self.args.positional

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
                pkgbuilds_paths=self.pkgbuilds_paths,
                manually_excluded_packages_names=self.manually_excluded_packages_names,
            )
        except PackagesNotFoundInAUR as exc:
            if exc.wanted_by:
                print_error(bold_line(
                    _("Dependencies missing for {}").format(', '.join(exc.wanted_by))
                ))
            print_not_found_packages(exc.packages)
            raise SysExit(131)
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
            raise SysExit(131)
        else:
            self.aur_deps_relations = self.install_info.aur_deps_relations

        if self.args.repo and self.not_found_repo_pkgs_names:
            print_not_found_packages(self.not_found_repo_pkgs_names, repo=True)
            raise SysExit(6)

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

    def manual_package_selection(self):  # pragma: no cover
        pkg_names_before = set(
            [
                update.name for update in (
                    self.install_info.repo_packages_install_info +
                    self.install_info.thirdparty_repo_packages_install_info +
                    self.install_info.aur_updates_install_info
                )
            ] + self.install_package_names + self.not_found_repo_pkgs_names
        )
        editor_cmd = get_editor_or_exit()
        if not editor_cmd:
            return
        text = pretty_format_sysupgrade(
            install_info=self.install_info,
            manual_package_selection=True
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
                set(strip_aur_repo_name(p) for p in selected_packages)
        ):
            self.manually_excluded_packages_names.append(pkg_name)
            if pkg_name in self.install_package_names:
                self.install_package_names.remove(pkg_name)
            if pkg_name in self.not_found_repo_pkgs_names:
                self.not_found_repo_pkgs_names.remove(pkg_name)

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

    def get_package_builds(self) -> None:  # pylint: disable=too-many-branches
        while self.all_aur_packages_names:
            try:
                clone_names = []
                pkgbuilds_by_base: Dict[str, PackageBuild] = {}
                pkgbuilds_by_name = {}
                for info in (
                        self.install_info.aur_updates_install_info +
                        self.install_info.aur_deps_install_info
                ):
                    if info.pkgbuild_path:
                        pkg_base = info.package.packagebase
                        if pkg_base not in pkgbuilds_by_base:
                            pkgbuilds_by_base[pkg_base] = PackageBuild(
                                pkgbuild_path=info.pkgbuild_path
                            )
                        pkgbuilds_by_name[info.name] = pkgbuilds_by_base[pkg_base]
                    else:
                        clone_names.append(info.name)
                self.package_builds_by_name = clone_aur_repos(clone_names)
                self.package_builds_by_name.update(pkgbuilds_by_name)
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
                else:  # pragma: no cover
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
                if answer == _("c"):  # pragma: no cover
                    package_build.git_reset_changed()
                elif answer == _("r"):  # pragma: no cover
                    remove_dir(package_build.repo_path)
                elif answer == _("s"):  # pragma: no cover
                    for skip_pkg_name in package_build.package_names:
                        self.discard_aur_package(skip_pkg_name)
                else:
                    raise SysExit(125)

    def ask_about_package_conflicts(self) -> None:
        if self.aur_packages_names:
            print_stderr(_('looking for conflicting AUR packages...'))
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
                    raise SysExit(125)
                self.resolved_conflicts.append([new_pkg_name, pkg_conflict])

    def ask_to_edit_file(
            self, filename: str, package_build: PackageBuild
    ) -> bool:  # pragma: no cover
        editor_cmd = get_editor_or_exit()
        if not editor_cmd:
            return False
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
        if ask_to_continue(
                _("Do you want to {edit} {file} for {name} package?").format(
                    edit=bold_line(_("edit")),
                    file=filename,
                    name=bold_line(', '.join(package_build.package_names)),
                ),
                default_yes=not (package_build.is_installed or
                                 PikaurConfig().build.get_bool("DontEditByDefault"))
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

    def _get_installed_status(self) -> None:
        all_package_builds = set(self.package_builds_by_name.values())
        with ThreadPool() as pool:
            threads = []
            for repo_status in all_package_builds:
                threads.append(
                    pool.apply_async(getattr, (repo_status, 'version_already_installed'))
                )
            for thread in threads:
                thread.get()
            pool.close()
            pool.join()
        for repo_status in all_package_builds:
            if self.args.needed and repo_status.version_already_installed:
                for package_name in repo_status.package_names:
                    print_package_uptodate(package_name, PackageSource.AUR)
                    self.discard_aur_package(package_name)
                if repo_status.reviewed:  # pragma: no cover
                    repo_status.update_last_installed_file()

    def review_build_files(self) -> None:  # pragma: no cover
        if self.args.needed or self.args.devel:
            self._get_installed_status()
        for repo_status in set(self.package_builds_by_name.values()):
            if repo_status.reviewed:
                continue
            if self.args.needed and repo_status.version_already_installed:
                continue
            if (
                    repo_status.build_files_updated
            ) and (
                repo_status.last_installed_hash
            ) and (
                repo_status.current_hash
            ) and (
                not self.args.noconfirm
            ):
                if not self.args.nodiff and ask_to_continue(
                        _("Do you want to see build files {diff} for {name} package?").format(
                            diff=bold_line(_("diff")),
                            name=bold_line(', '.join(repo_status.package_names))
                        )
                ):
                    git_args = [
                        'git',
                        '-C',
                        repo_status.repo_path,
                        'diff',
                        '--ignore-space-change',
                        '--ignore-all-space',
                        '--unified={line_count}'.format(line_count=PikaurConfig().ui.get_int('DiffContext')),
                        repo_status.last_installed_hash,
                        repo_status.current_hash,
                    ]
                    diff_pager = PikaurConfig().ui.DiffPager
                    if diff_pager == 'always':
                        git_args = ['env', 'GIT_PAGER=less -+F'] + git_args
                    elif diff_pager == 'never':
                        git_args = ['env', 'GIT_PAGER=cat'] + git_args
                    interactive_spawn(git_args)
            src_info = SrcInfo(pkgbuild_path=repo_status.pkgbuild_path)

            if self.ask_to_edit_file(
                    os.path.basename(repo_status.pkgbuild_path), repo_status
            ):
                src_info.regenerate()
                # @TODO: recompute AUR deps
                for pkg_name in repo_status.package_names:
                    install_src_info = SrcInfo(
                        pkgbuild_path=repo_status.pkgbuild_path,
                        package_name=pkg_name
                    )
                    install_file_name = install_src_info.get_install_script()
                    if install_file_name:
                        self.ask_to_edit_file(install_file_name, repo_status)

            check_pkg_arch(repo_status)
            repo_status.reviewed = True

    def build_packages(self) -> None:  # pylint: disable=too-many-branches
        if self.args.needed or self.args.devel:
            self._get_installed_status()

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
                packages_to_be_built.remove(pkg_name)
                continue

            try:
                repo_status.build(
                    all_package_builds=self.package_builds_by_name,
                    resolved_conflicts=self.resolved_conflicts
                )
            except (BuildError, DependencyError) as exc:
                print_stderr(exc)
                print_stderr(
                    color_line(_("Can't build '{name}'.").format(name=pkg_name) + '\n', 9)
                )
                # if not ask_to_continue():
                #     raise SysExit(125)
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
                        print_error(
                            _("Dependency cycle detected between {}").format(deps_fails_counter)
                        )
                        raise SysExit(131)
            else:
                for _pkg_name in repo_status.package_names:
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
        for excluded_pkg_name in self.manually_excluded_packages_names + (self.args.ignore or []):
            extra_args.append('--ignore')
            extra_args.append(excluded_pkg_name)
        if not retry_interactive_command(
                sudo(
                    get_pacman_command() + [
                        '--sync',
                    ] + reconstruct_args(self.args, ignore_args=[
                        'sync',
                        'refresh',
                        'ignore',
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
            if self.package_builds_by_name[pkg_name].built_packages_paths.get(pkg_name) and
            not self.package_builds_by_name[pkg_name].built_packages_installed.get(pkg_name)
        }
        try:
            install_built_deps(
                deps_names_and_paths=new_aur_deps_to_install,
                resolved_conflicts=self.resolved_conflicts
            )
        except DependencyError:
            if not ask_to_continue(default_yes=False):
                self._revert_transaction(PackageSource.AUR)
                raise SysExit(125)
        else:
            self._save_transaction(
                PackageSource.AUR, installed=list(new_aur_deps_to_install.keys())
            )

    def install_aur_packages(self) -> None:
        aur_packages_to_install = {
            pkg_name: self.package_builds_by_name[pkg_name].built_packages_paths[pkg_name]
            for pkg_name in self.aur_packages_names
            if self.package_builds_by_name[pkg_name].built_packages_paths.get(pkg_name) and
            not self.package_builds_by_name[pkg_name].built_packages_installed.get(pkg_name)
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

    def install_packages(self):

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
                    if not package_build.keep_build_dir:
                        remove_dir(package_build.build_dir)

        if self.failed_to_build_package_names:
            print_stderr('\n'.join(
                [color_line(_("Failed to build following packages:"), 9), ] +
                self.failed_to_build_package_names
            ))
            raise SysExit(1)
