#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import asyncio
import argparse
import subprocess
import readline
import shutil
import glob
import ssl
import email
import json
from urllib.parse import urlencode


CACHE_ROOT = os.path.expanduser('~/.cache/pikaur/')
AUR_REPOS_CACHE = os.path.join(CACHE_ROOT, 'aur_repos')
PKG_CACHE = os.path.join(CACHE_ROOT, 'pkg')
BUILD_CACHE = os.path.join(CACHE_ROOT, 'build')
LOCK_FILE_PATH = os.path.join(CACHE_ROOT, 'db.lck')


def init_readline():
    # follow GNU readline config in prompts:
    system_inputrc_path = '/etc/inputrc'
    if os.path.exists(system_inputrc_path):
        readline.read_init_file(system_inputrc_path)
    user_inputrc_path = os.path.expanduser('~/.inputrc')
    if os.path.exists(user_inputrc_path):
        readline.read_init_file(user_inputrc_path)


init_readline()


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

    async def _read_stream(self, stream, callback):
        while True:
            line = await stream.readline()
            if line:
                if self.enable_logging:
                    print('>> {}'.format(line.decode('ascii')), end='')
                callback(line)
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
    loop = None

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


class SingleTaskExecutor(MultipleTasksExecutor):

    def __init__(self, cmd):
        super().__init__({0: cmd})

    def execute(self):
        return super().execute()[0]


def color_line(line, color_number):
    result = ''
    if color_number >= 8:
        result += "\033[1m"
        color_number -= 8
    result += f"\033[03{color_number}m{line}"
    # reset font:
    result += "\033[0m"
    return result


def format_paragraph(line):
    PADDING = 4
    term_width = shutil.get_terminal_size((80, 80)).columns
    max_line_width = term_width - PADDING * 2

    result = []
    current_line = []
    line_length = 0
    for word in line.split():
        if len(word) + line_length > max_line_width:
            result.append(current_line)
            current_line = []
            line_length = 0
        current_line.append(word)
        line_length += len(word) + 1
    result.append(current_line)

    return '\n'.join([
        ' '.join(
            [(PADDING-1)*' ', ] +
            words +
            [(PADDING-1)*' ', ],
        )
        for words in result
    ])


def find_pacman_packages(packages, local=False):
    result = SingleTaskExecutor(
        PacmanTaskWorker(['-Ssq', ] if not local else ['-Qsq', ])
    ).execute()
    all_repo_packages = result.stdout.splitlines()
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


class NetworkTaskResult():
    return_code = None
    headers = None
    json = None

    @classmethod
    def from_bytes(cls, bytes_response):
        # prepare response for parsing:
        request_result, the_rest = bytes_response.split(b'\r\n', 1)
        request_result = request_result.decode()
        # parse reponse:
        parsed_response = email.message_from_bytes(the_rest)
        # from email.policy import EmailPolicy
        # parsed_response = email.message_from_bytes(
        #    headers, policy=EmailPolicy
        # )
        headers = dict(parsed_response.items())
        # join chunked response parts into one:
        payload = ''
        if headers.get('Transfer-Encoding') == 'chunked':
            all_lines = parsed_response._payload.split('\r\n')
            while all_lines:
                length = int('0x' + all_lines.pop(0), 16)
                if length == 0:
                    break
                payload += all_lines.pop(0)
        else:
            payload = parsed_response._payload

        # save result:
        self = cls()
        self.return_code = request_result.split()[1]
        self.headers = headers
        self.json = json.loads(payload)
        return self


async def https_client_task(loop, host, uri, port=443):
    # open SSL connection:
    ssl_context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
    )
    reader, writer = await asyncio.open_connection(
        host, port,
        ssl=ssl_context, loop=loop
    )

    # prepare request data:
    action = f'GET {uri} HTTP/1.1\r\n'
    headers = '\r\n'.join([
        f'{key}: {value}' for key, value in {
            "Host": host,
            "Content-type": "application/json",
            "User-Agent": "pikaur/0.1",
            "Accept": "*/*"
        }.items()
    ]) + '\r\n'
    body = '\r\n' + '\r\n'
    request = f'{action}{headers}{body}\x00'
    # send request:
    writer.write(request.encode())
    await writer.drain()

    # read response:
    data = await reader.read()
    # close the socket:
    writer.close()
    return NetworkTaskResult.from_bytes(data)


class AurTaskWorker():

    host = 'aur.archlinux.org'
    uri = None

    def get_task(self, loop):
        return https_client_task(loop, self.host, self.uri)


class AurTaskWorker_Search(AurTaskWorker):

    def __init__(self, search_query):
        params = urlencode({
            'v': 5,
            'type': 'search',
            'arg': search_query,
            'by': 'name-desc'
        })
        self.uri = f'/rpc/?{params}'


class AurTaskWorker_Info(AurTaskWorker):

    def __init__(self, packages):
        params = urlencode({
            'v': 5,
            'type': 'info',
        })
        for package in packages:
            params += '&arg[]=' + package
        self.uri = f'/rpc/?{params}'


def get_repo_url(package_name):
    return f'https://aur.archlinux.org/{package_name}.git'


def find_aur_packages(package_names):
    result = SingleTaskExecutor(
        AurTaskWorker_Info(packages=package_names)
    ).execute()
    json_results = result.json['results']
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

    built_package_path = None

    def __init__(self, package_name):
        self.package_name = package_name
        repo_path = os.path.join(AUR_REPOS_CACHE, package_name)
        if os.path.exists(repo_path):
            # pylint: disable=simplifiable-if-statement
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
        return NotImplemented


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


def get_editor():
    editor = os.environ.get('EDITOR')
    if editor:
        return editor
    for editor in ('vim', 'nano', 'mcedit', 'edit'):
        result = SingleTaskExecutor(
            CmdTaskWorker(['which', editor])
        ).execute()
        if result.return_code == 0:
            return editor
    print(
        '{} {}'.format(
            color_line('error:', 9),
            'no editor found. Try setting $EDITOR.'
        )
    )
    if not ask_to_continue('Do you want to proceed without editing?'):
        sys.exit(2)


def cli_install_packages(args):
    pacman_packages, aur_packages = find_repo_packages(args.positional)
    new_aur_deps = find_aur_deps(aur_packages)

    # confirm package install/upgrade
    print()
    # print(color_line("Package", 15))
    if pacman_packages:
        print(color_line("New packages will be installed:", 12))
        print(format_paragraph(' '.join(pacman_packages)))
    if aur_packages:
        print(color_line("New packages will be installed from AUR:", 14))
        print(format_paragraph(' '.join(aur_packages)))
    if new_aur_deps:
        print(color_line("New dependencies will be installed from AUR:", 11))
        print(format_paragraph(' '.join(new_aur_deps)))
    print()

    answer = input('{} {}\n{} {}\n'.format(
        color_line('::', 12),
        color_line('Proceed with installation? [Y/n] ', 15),
        color_line('::', 12),
        color_line('[V]iew package detail   [M]anually select packages', 15)
    ))
    if answer and answer.lower()[0] != 'y':
        sys.exit(1)

    all_aur_package_names = aur_packages + new_aur_deps
    repos_statuses = None
    if all_aur_package_names:
        repos_statuses = clone_git_repos(all_aur_package_names)

    # review PKGBUILD and install files @TODO:
    for pkg_name in reversed(all_aur_package_names):
        repo_status = repos_statuses[pkg_name]
        repo_path = repo_status.repo_path

        last_installed_file = os.path.join(
            repo_path,
            'last_installed.txt'
        )
        already_installed = False
        if os.path.exists(last_installed_file):
            with open(last_installed_file) as f:
                last_installed_hash = f.readlines()
                with open(last_installed_file) as f2:
                    os.path.join(
                        repo_path,
                        '.git/refs/heads/master'
                    )
                    current_hash = f2.readlines()
                    if last_installed_hash == current_hash:
                        already_installed = True
        repo_status.already_installed = already_installed

        if not ('--needed' in args.raw and already_installed):
            if ask_to_continue(
                    "Do you want to edit PKGBUILD for {} package?".format(
                        color_line(pkg_name, 15)
                    ),
                    default_yes=False
            ) and get_editor():
                interactive_spawn([
                    get_editor(),
                    os.path.join(
                        repo_path,
                        'PKGBUILD'
                    )
                ])
        else:
            print(
                '{} {} {}'.format(
                    color_line('warning:', 11),
                    pkg_name,
                    'is up to date -- skipping'
                )
            )

    # get sudo for further questions
    interactive_spawn([
        'sudo', 'true'
    ])

    # build packages
    for pkg_name in reversed(all_aur_package_names):
        repo_status = repos_statuses[pkg_name]

        if '--needed' in args.raw and repo_status.already_installed:
            continue
        repo_path = repo_status.repo_path
        build_dir = os.path.join(BUILD_CACHE, pkg_name)
        if os.path.exists(build_dir):
            try:
                shutil.rmtree(build_dir)
            except PermissionError:
                interactive_spawn(['rm', '-rf', build_dir])
        shutil.copytree(repo_path, build_dir)

        interactive_spawn(
            [
                'makepkg',
                '-rf',
                '--nodeps'
            ],
            cwd=build_dir
        )
        repo_status.built_package_path = glob.glob(
            os.path.join(build_dir, '*.pkg.tar.xz')
        )[0]

    if pacman_packages:
        interactive_spawn(
            [
                'sudo',
                'pacman',
                '-S',
                '--noconfirm',
            ] + args.unknown_args +
            pacman_packages,
        )

    new_aur_deps_to_install = [
        repos_statuses[pkg_name].built_package_path
        for pkg_name in new_aur_deps
        if repos_statuses[pkg_name].built_package_path
    ]
    if new_aur_deps_to_install:
        interactive_spawn(
            [
                'sudo',
                'pacman',
                '-U',
                '--asdeps',
                '--noconfirm',
            ] + args.unknown_args +
            new_aur_deps_to_install,
        )

    aur_packages_to_install = [
        repos_statuses[pkg_name].built_package_path
        for pkg_name in aur_packages
        if repos_statuses[pkg_name].built_package_path
    ]
    if aur_packages_to_install:
        interactive_spawn(
            [
                'sudo',
                'pacman',
                '-U',
                '--noconfirm',
            ] + args.unknown_args +
            aur_packages_to_install,
        )

    # save git hash of last sucessfully installed package
    if repos_statuses:
        for pkg_name, repo_status in repos_statuses.items():
            shutil.copy2(
                os.path.join(
                    repo_status.repo_path,
                    '.git/refs/heads/master'
                ),
                os.path.join(
                    repo_status.repo_path,
                    'last_installed.txt'
                )
            )


def cli_upgrade_package(_args):
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


def cli_search_packages(args):
    PKGS = 'pkgs'
    AUR = 'aur'
    result = MultipleTasksExecutor({
        PKGS: PacmanColorTaskWorker(args.raw),
        AUR: AurTaskWorker_Search(search_query=' '.join(args.positional or [])),
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
            print(format_paragraph(f'{aur_pkg["Description"]}'))
        # print(aur_pkg)


def parse_args(args):
    parser = argparse.ArgumentParser(prog=sys.argv[0])
    for letter in ('S', 's', 'q', 'u', 'y'):
        parser.add_argument('-'+letter, action='store_true')
    parser.add_argument('positional', nargs='?')
    parsed_args, unknown_args = parser.parse_known_args(args)
    parsed_args.unknown_args = unknown_args
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
    if os.getuid() == 0:
        print("{} {}".format(
            color_line('::', 9),
            "Don't run me as root."
        ))
        sys.exit(1)
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
