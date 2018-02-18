#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
# import argparse
import readline

from .args import parse_args
from .core import (
    MultipleTasksExecutor, interactive_spawn,
)
from .pprint import (
    color_line, bold_line, format_paragraph,
    print_not_found_packages,
    print_upgradeable, pretty_print_upgradeable,
    print_version,
)
from .aur import (
    AurTaskWorkerSearch, AurTaskWorkerInfo,
)
from .pacman import (
    PacmanColorTaskWorker, PackageDB,
    find_packages_not_from_repo,
)
from .meta_package import (
    find_repo_updates, find_aur_updates, exclude_ignored_packages,
)
from .install_cli import InstallPackagesCLI


def init_readline():
    # follow GNU readline config in prompts:
    system_inputrc_path = '/etc/inputrc'
    if os.path.exists(system_inputrc_path):
        readline.read_init_file(system_inputrc_path)
    user_inputrc_path = os.path.expanduser('~/.inputrc')
    if os.path.exists(user_inputrc_path):
        readline.read_init_file(user_inputrc_path)


init_readline()


def cli_print_upgradeable(args):
    updates, _ = find_aur_updates(find_packages_not_from_repo())
    updates += find_repo_updates()
    updates = sorted(updates, key=lambda u: u.Name)
    if args.quiet:
        print_upgradeable(updates)
    else:
        pretty_print_upgradeable(updates)


def cli_install_packages(args, packages=None):
    InstallPackagesCLI(args=args, packages=packages)


def cli_upgrade_packages(args):
    if args.refresh:
        interactive_spawn(['sudo', 'pacman', '--sync', '--refresh'])
    ignore = args.ignore or []

    print('{} {}'.format(
        color_line('::', 12),
        bold_line('Starting full system upgrade...')
    ))
    repo_packages_updates = [
        pkg for pkg in find_repo_updates()
        if pkg.Name not in ignore
    ]

    print('{} {}'.format(
        color_line('::', 12),
        bold_line('Starting full AUR upgrade...')
    ))
    aur_updates, not_found_aur_pkgs = \
        find_aur_updates(find_packages_not_from_repo())
    exclude_ignored_packages(not_found_aur_pkgs, args)
    if not_found_aur_pkgs:
        print_not_found_packages(sorted(not_found_aur_pkgs))
    aur_updates = [
        pkg for pkg in aur_updates
        if pkg.Name not in ignore
    ]

    all_upgradeable_package_names = [
        u.Name for u in repo_packages_updates
    ] + [
        u.Name for u in aur_updates
    ]
    all_package_names = list(set(all_upgradeable_package_names + args.positional))
    if all_package_names:
        cli_install_packages(
            args=args,
            packages=all_package_names,
        )
    else:
        print('\n{} {}'.format(
            color_line('::', 10),
            bold_line('Already up-to-date.')
        ))


def cli_info_packages(args):
    pkgs = 'pkgs'
    aur = 'aur'
    result = MultipleTasksExecutor({
        pkgs: PacmanColorTaskWorker(args.raw),
        aur: AurTaskWorkerInfo(
            packages=args.positional or []
        ),
    }).execute()
    aur_pkgs = result[aur]
    num_found = len(aur_pkgs)
    if result[pkgs].stdout:
        print(result[pkgs].stdout, end='\n' if aur_pkgs else '')
    for i, aur_pkg in enumerate(aur_pkgs):
        print(
            '\n'.join([
                '{key:24}: {value}'.format(
                    key=bold_line(key),
                    value=value if not isinstance(value, list)
                    else ', '.join(value)
                )
                for key, value in aur_pkg.__dict__.items()
            ]) + ('\n' if i+1 < num_found else '')
        )


def cli_clean_packages_cache(_args):
    print(_args)
    # @TODO: implement -Sc and -Scc
    raise NotImplementedError()


def cli_search_packages(args):

    class GetLocalPkgsVersionsTask():
        async def get_task(self):
            return {
                pkg_name: pkg.Version
                for pkg_name, pkg in PackageDB.get_local_dict().items()
            }

    repo = 'repo'
    aur = 'aur'
    local = 'local'
    tasks = {
        repo: PacmanColorTaskWorker(args.raw),
        local: GetLocalPkgsVersionsTask,
    }
    tasks.update({
        aur+search_word: AurTaskWorkerSearch(search_query=search_word)
        for search_word in (args.positional or [])
    })
    result = MultipleTasksExecutor(tasks).execute()
    local_pkgs_versions = result[local]
    local_pkgs_names = local_pkgs_versions.keys()

    all_aur_results = {
        key: search_results for key, search_results in result.items()
        if key.startswith(aur)
    }
    aur_pkgs_nameset = None
    for key, search_results in all_aur_results.items():
        new_aur_pkgs_nameset = set([result.Name for result in search_results])
        if aur_pkgs_nameset:
            aur_pkgs_nameset = aur_pkgs_nameset.intersection(new_aur_pkgs_nameset)
        else:
            aur_pkgs_nameset = new_aur_pkgs_nameset
    aur_result = {
        result.Name: result
        for key, search_results in all_aur_results.items()
        for result in search_results
        if result.Name in aur_pkgs_nameset
    }.values()

    if result[repo].stdout != '':
        print(result[repo].stdout)
    for aur_pkg in sorted(
            aur_result,
            key=lambda pkg: (pkg.NumVotes + 0.1) * (pkg.Popularity + 0.1),
            reverse=True
    ):
        # @TODO: return only packages for the current architecture
        pkg_name = aur_pkg.Name
        if args.quiet:
            print(pkg_name)
        else:
            print("{}{} {} {}({}, {:.2f})".format(
                # color_line('aur/', 13),
                color_line('aur/', 9),
                bold_line(pkg_name),
                color_line(aur_pkg.Version, 10),
                color_line('[installed{}] '.format(
                    f': {local_pkgs_versions[pkg_name]}'
                    if aur_pkg.Version != local_pkgs_versions[pkg_name]
                    else ''
                ), 14) if pkg_name in local_pkgs_names else '',
                aur_pkg.NumVotes,
                aur_pkg.Popularity
            ))
            print(format_paragraph(f'{aur_pkg.Description}'))


def cli_entry_point():
    # pylint: disable=too-many-branches
    raw_args = sys.argv[1:]
    args = parse_args(raw_args)

    not_implemented_in_pikaur = False
    require_sudo = True

    if args.sync:
        if args.sysupgrade:
            cli_upgrade_packages(args)
        elif args.search:
            cli_search_packages(args)
        elif args.info:
            cli_info_packages(args)
        elif args.clean:
            cli_clean_packages_cache(args)
        elif '-S' in raw_args or '--sync' in raw_args:
            cli_install_packages(args)
        elif args.groups:
            not_implemented_in_pikaur = True
            require_sudo = False
        else:
            not_implemented_in_pikaur = True

    elif args.query:
        if args.sysupgrade:
            cli_print_upgradeable(args)
        else:
            not_implemented_in_pikaur = True
            require_sudo = False

    elif args.version:
        print_version()
    else:
        not_implemented_in_pikaur = True

    if args.help:
        require_sudo = False

    if not_implemented_in_pikaur:
        if require_sudo:
            sys.exit(
                interactive_spawn(['sudo', 'pacman', ] + raw_args).returncode
            )
        sys.exit(
            interactive_spawn(['pacman', ] + raw_args).returncode
        )


def main():
    if os.getuid() == 0:
        print("{} {}".format(
            color_line('::', 9),
            "Don't run me as root."
        ))
        sys.exit(1)
    try:
        cli_entry_point()
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)


if __name__ == '__main__':
    main()
