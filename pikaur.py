#!/usr/bin/env python3

import os
import sys
import asyncio
import argparse
import subprocess
import readline
import shutil
import glob

from aur import (
    AurTaskWorker_Search, AurTaskWorker_Info,
    get_repo_url,
)


CACHE_ROOT = os.path.expanduser('~/.cache/pikaur/')
AUR_REPOS_CACHE = os.path.join(CACHE_ROOT, 'aur_repos')
PKG_CACHE = os.path.join(CACHE_ROOT, 'pkg')
BUILD_CACHE = os.path.join(CACHE_ROOT, 'build')
LOCK_FILE_PATH = os.path.join(CACHE_ROOT, 'db.lck')


# follow GNU readline config in prompts:
system_inputrc_path = '/etc/inputrc'
if os.path.exists(system_inputrc_path):
    readline.read_init_file(system_inputrc_path)
user_inputrc_path = os.path.expanduser('~/.inputrc')
if os.path.exists(user_inputrc_path):
    readline.read_init_file(user_inputrc_path)


class CmdTaskResult():
    stderr = None
    stdout = None
    return_code = None

    def __repr__(self):
        result = f"[rc: {self.return_code}]\n"
        if self.stderr:
            result += '\n'.join([
                "=======",
                "errors:",
                "=======",
                "{}".format(self.stderr)
            ])
        result += '\n'.join([
            "-------",
            "output:",
            "-------",
            "{}".format(self.stdout)
        ])
        return result


class CmdTaskWorker(object):
    cmd = None
    stderr = None
    stdout = None
    enable_logging = None
    # enable_logging = True

    async def _read_stream(self, stream, cb):
        while True:
            line = await stream.readline()
            if line:
                if self.enable_logging:
                    print('>> {}'.format(line.decode('ascii')), end='')
                cb(line)
            else:
                break

    def save_err(self, line):
        self.stderr += line

    def save_out(self, line):
        self.stdout += line

    async def _stream_subprocess(self):
        process = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        # print(f"== STARTED {self.cmd}")
        await asyncio.wait([
            self._read_stream(process.stdout, self.save_out),
            self._read_stream(process.stderr, self.save_err)
        ])
        # print(f"== DEBUG {self.cmd}")
        result = CmdTaskResult()
        result.return_code = await process.wait()
        # print(f"== DONE with {result.return_code}")
        result.stderr = self.stderr.decode('ascii')
        result.stdout = self.stdout.decode('ascii')
        return result

    def __init__(self, cmd):
        self.cmd = cmd
        self.stderr = b''
        self.stdout = b''

    def get_task(self, _loop):
        return self._stream_subprocess()


class PacmanTaskWorker(CmdTaskWorker):

    def __init__(self, args):
        super().__init__(
            [
                "pacman",
            ] + args
        )


class PacmanColorTaskWorker(PacmanTaskWorker):

    def __init__(self, args):
        super().__init__(
            [
                "--color=always",
            ] + args
        )


class MultipleTasksExecutor(object):

    def __init__(self, cmds):
        self.cmds = cmds
        self.results = {}
        self.futures = {}

    def create_process_done_callback(self, cmd_id):

        def _process_done_callback(future):
            result = future.result()
            self.results[cmd_id] = result
            if len(self.results) == len(self.futures):
                # print('== LOOP STOP')
                self.loop.stop()

        return _process_done_callback

    def execute(self):
        self.loop = asyncio.get_event_loop()
        # if self.loop.is_closed():
        #     self.loop = asyncio.new_event_loop()
        for cmd_id, task_class in self.cmds.items():
            future = self.loop.create_task(
                task_class.get_task(self.loop)
            )
            future.add_done_callback(self.create_process_done_callback(cmd_id))
            self.futures[cmd_id] = future
        self.loop.run_forever()
        # print('== LOOP CLOSE')
        # self.loop.close()
        return self.results


def color_line(line, color_number):
    result = ''
    if color_number >= 8:
        result += "\033[1m"
        color_number -= 8
    result += f"\033[03{color_number}m{line}"
    # reset font:
    result += "\033[0m"
    return result


def cli_search_packages(args):
    PKGS = 'pkgs'
    AUR = 'aur'
    result = MultipleTasksExecutor({
        PKGS: PacmanColorTaskWorker(args.raw),
        AUR: AurTaskWorker_Search(search_query=' '.join(args.positional)),
    }).execute()

    print(result[PKGS].stdout, end='')
    for aur_pkg in result[AUR].json['results']:
        if args.q:
            print(aur_pkg['Name'])
        else:
            print("{}{} {} {}".format(
                # color_line('aur/', 13),
                color_line('aur/', 9),
                color_line(aur_pkg['Name'], 15),
                color_line(aur_pkg["Version"], 10),
                '',  # [installed]
            ))
            print(f'    {aur_pkg["Description"]}')
        # print(aur_pkg)


def find_pacman_packages(packages, local=False):
    results = MultipleTasksExecutor({
        0: PacmanTaskWorker(['-Ssq', ] if not local else ['-Qsq', ])
    }).execute()
    all_repo_packages = results[0].stdout.splitlines()
    pacman_packages = []
    not_found_packages = []
    for package_name in packages:
        if package_name not in all_repo_packages:
            not_found_packages.append(package_name)
        else:
            pacman_packages.append(package_name)
    return pacman_packages, not_found_packages


def find_repo_packages(packages):
    return find_pacman_packages(packages, local=False)


def find_local_packages(packages):
    return find_pacman_packages(packages, local=True)


def find_aur_packages(package_names):
    results = MultipleTasksExecutor({
        0: AurTaskWorker_Info(packages=package_names),
    }).execute()
    json_results = results[0].json['results']
    found_aur_packages = [
        result['Name'] for result in json_results
    ]
    if len(package_names) != len(found_aur_packages):
        print("Not found in AUR:")
        for package in package_names:
            if package not in found_aur_packages:
                print(package)
        sys.exit(1)
    return json_results


def find_aur_deps(package_names):
    new_aur_deps = []
    while package_names:

        all_deps_for_aur_packages = []
        for result in find_aur_packages(package_names):
            all_deps_for_aur_packages += [
                dep.split('=')[0].split('<')[0].split('>')[0] for dep in
                result.get('Depends', []) + result.get('MakeDepends', [])
            ]
        all_deps_for_aur_packages = list(set(all_deps_for_aur_packages))

        aur_deps_for_aur_packages = []
        if all_deps_for_aur_packages:
            _, not_found_deps = find_repo_packages(
                all_deps_for_aur_packages
            )
            if not_found_deps:
                _, aur_deps_for_aur_packages = find_local_packages(
                    not_found_deps
                )
                find_aur_packages(aur_deps_for_aur_packages)
        new_aur_deps += aur_deps_for_aur_packages
        package_names = aur_deps_for_aur_packages

    return new_aur_deps


def ask_to_continue(text='Do you want to proceed?', default_yes=True):
    answer = input(text + (' [Y/n] ' if default_yes else ' [y/N] '))
    if default_yes:
        if answer and answer.lower()[0] != 'y':
            return False
    else:
        if not answer or answer.lower()[0] != 'y':
            return False
    return True


class GitRepoStatus():
    repo_path = None
    clone = False
    pull = False

    package_name = None

    def __init__(self, package_name):
        self.package_name = package_name
        repo_path = os.path.join(AUR_REPOS_CACHE, package_name)
        if os.path.exists(repo_path):
            if os.path.exists(os.path.join(repo_path, '.git')):
                self.pull = True
            else:
                self.clone = True
        else:
            os.makedirs(repo_path)
            self.clone = True
        self.repo_path = repo_path

    def create_clone_task(self):
        return CmdTaskWorker([
            'git',
            'clone',
            get_repo_url(self.package_name),
            self.repo_path,
        ])

    def create_pull_task(self):
        return CmdTaskWorker([
            'git',
            '-C',
            self.repo_path,
            'pull',
            'origin',
            'master'
        ])

    def create_task(self):
        if self.pull:
            return self.create_pull_task()
        elif self.clone:
            return self.create_clone_task()


def clone_git_repos(package_names):
    repos_statuses = {
        package_name: GitRepoStatus(package_name)
        for package_name in package_names
    }
    results = MultipleTasksExecutor({
        repo_status.package_name: repo_status.create_task()
        for repo_status in repos_statuses.values()
    }).execute()
    for package_name, result in results.items():
        if result.return_code > 0:
            print(color_line(f"Can't clone '{package_name}' from AUR:", 9))
            print(result)
            if not ask_to_continue():
                sys.exit(1)
    return repos_statuses


def cli_install_packages(args):
    pacman_packages, aur_packages = find_repo_packages(args.positional)
    new_aur_deps = find_aur_deps(aur_packages)

    # confirm package install/upgrade
    print()
    # print(color_line("Package", 15))
    print(color_line("Packages:", 12))
    for pkg in pacman_packages:
        print(pkg)
    for pkg in aur_packages:
        print(pkg)
    if new_aur_deps:
        print(color_line("New dependencies will be installed from AUR:", 11))
        for dep in new_aur_deps:
            print(dep)
    print()
    print('{} {}'.format(
        color_line('::', 12),
        color_line('Proceed with installation? [Y/n]', 15)
    ))
    print('{} {}'.format(
        color_line('::', 12),
        color_line('[V]iew package detail   [M]anually select packages', 15)
    ))
    answer = input()
    if answer and answer.lower()[0] != 'y':
        return

    all_aur_package_names = aur_packages + new_aur_deps
    repos_statuses = clone_git_repos(all_aur_package_names)

    # review PKGBUILD and install files
    for pkg_name in reversed(all_aur_package_names):
        if ask_to_continue(
            "Do you want to edit PKGBUILD for {} package?".format(
                color_line(pkg_name, 15)
            ),
            default_yes=False
        ):
            interactive_spawn([
                os.environ.get('EDITOR', 'vim'),
                os.path.join(
                    repos_statuses[pkg_name].repo_path,
                    'PKGBUILD'
                )
            ])

    built_packages_paths = {}
    interactive_spawn([
        'sudo', 'echo'
    ])
    for pkg_name in reversed(all_aur_package_names):
        build_dir = os.path.join(BUILD_CACHE, pkg_name)
        if os.path.exists(build_dir):
            shutil.rmtree(build_dir)
        shutil.copytree(repos_statuses[pkg_name].repo_path, build_dir)
        interactive_spawn(
            [
                'makepkg',
                '-rf',
                '--nodeps'
            ],
            cwd=build_dir
        )
        built_packages_paths[pkg_name] = glob.glob(
            os.path.join(build_dir, '*.pkg.tar.xz')
        )[0]
        print(built_packages_paths[pkg_name])

    if pacman_packages:
        interactive_spawn(
            [
                'echo',
                'sudo',
                'pacman',
                '-S',
                '--noconfirm',
            ] + pacman_packages,
        )
    if new_aur_deps:
        interactive_spawn(
            [
                'echo',
                'sudo',
                'pacman',
                '-U',
                '--asdeps',
                '--noconfirm',
            ] + [
                built_packages_paths[pkg_name]
                for pkg_name in new_aur_deps
            ],
        )
    # sudo pacman -U --asdeps aur_deps_for_aur
    # sudo pacman -U aur_packages
    # write last_installed.txt


def cli_upgrade_package(args):
    result = MultipleTasksExecutor({
        'proc1': CmdTaskWorker([
            "bash", "-c",
            "echo stdout"
            " && sleep 1"
            " && echo stderr 1>&2"
            " && sleep 1"
            " && echo done"
        ]),
        'proc2': CmdTaskWorker([
            "bash", "-c",
            "echo stdout2"
            " && sleep 1"
            " && echo stderr2 1>&2"
            " && sleep 1"
            " && echo done2"
        ]),
    }).execute()
    print(result)


def parse_args(args):
    parser = argparse.ArgumentParser(prog=sys.argv[0])
    for letter in ('S', 's', 'q', 'u', 'y'):
        parser.add_argument('-'+letter, action='store_true')
    parser.add_argument('positional', nargs='+')
    parsed_args, unknown_args = parser.parse_known_args(args)
    parsed_args.raw = args

    # print(f'args = {args}')
    # print("ARGPARSE:")
    # print(parsed_args)
    # print(unknown_args)

    return parsed_args


def interactive_spawn(cmd, **kwargs):
    subprocess.Popen(cmd, **kwargs).communicate()


def main():
    args = sys.argv[1:]
    parsed_args = parse_args(args)

    if parsed_args.S:
        if parsed_args.u:
            return cli_upgrade_package(parsed_args)
        elif parsed_args.s:
            return cli_search_packages(parsed_args)
        elif '-S' in args:
            return cli_install_packages(parsed_args)

    interactive_spawn(['pacman', ] + args)


if __name__ == '__main__':
    main()
