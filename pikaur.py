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
from distutils.version import LooseVersion


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


def interactive_spawn(cmd, **kwargs):
    process = subprocess.Popen(cmd, **kwargs)
    process.communicate()
    return process


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

    async def _read_stream(self, stream, callback):
        while True:
            line = await stream.readline()
            if line:
                if self.enable_logging:
                    print('>> {}'.format(line.decode('utf-8')), end='')
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
        await asyncio.wait([
            self._read_stream(process.stdout, self.save_out),
            self._read_stream(process.stderr, self.save_err)
        ])
        result = CmdTaskResult()
        result.return_code = await process.wait()
        result.stderr = self.stderr.decode('utf-8')
        result.stdout = self.stdout.decode('utf-8')
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
                self.loop.stop()

        return _process_done_callback

    def execute(self):
        self.loop = asyncio.get_event_loop()
        for cmd_id, task_class in self.cmds.items():
            future = self.loop.create_task(
                task_class.get_task(self.loop)
            )
            future.add_done_callback(self.create_process_done_callback(cmd_id))
            self.futures[cmd_id] = future
        if self.loop.is_running():
            print("DEBUG989817")
        self.loop.run_forever()
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
    padding = 4
    term_width = shutil.get_terminal_size((80, 80)).columns
    max_line_width = term_width - padding * 2

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
            [(padding-1)*' ', ] +
            words +
            [(padding-1)*' ', ],
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


def find_packages_not_from_repo():
    local_prefix = 'local/'
    result = SingleTaskExecutor(
        PacmanTaskWorker(['-Qs', ])
    ).execute()
    all_local_packages_versions = {}
    for line in result.stdout.splitlines():
        if line.startswith(local_prefix):
            pkg_name, version = line.split()[:2]
            pkg_name = pkg_name.split(local_prefix)[1]
            all_local_packages_versions[pkg_name] = version

    repo_packages, not_found_packages = find_repo_packages(
        all_local_packages_versions.keys()
    )
    not_found_packages_versions = {
        pkg_name: all_local_packages_versions[pkg_name]
        for pkg_name in not_found_packages
    }
    return not_found_packages_versions


def find_repo_updates():
    result = SingleTaskExecutor(
        PacmanTaskWorker(['-Qu', ])
    ).execute()
    packages_updates_lines = result.stdout.splitlines()
    repo_packages_updates = []
    for update in packages_updates_lines:
        pkg_name, current_version, _, new_version, *_ = update.split()
        repo_packages_updates.append(
            AurUpdate(
                pkg_name=pkg_name,
                aur_version=new_version,
                current_version=current_version,
            )
        )
    return repo_packages_updates


class NetworkTaskResult():
    return_code = None
    headers = None
    json = None

    @classmethod
    def from_bytes(cls, bytes_response):
        # prepare response for parsing:
        bytes_response = bytes_response.decode('utf-8')
        request_result, the_rest = bytes_response.split('\r\n', 1)
        # parse reponse:
        parsed_response = email.message_from_string(the_rest)
        # from email.policy import EmailPolicy
        # parsed_response = email.message_from_string(
        #    headers, policy=EmailPolicy
        # )
        headers = dict(parsed_response.items())
        # join chunked response parts into one:
        payload = ''
        if headers.get('Transfer-Encoding') == 'chunked':
            all_lines = parsed_response.get_payload().split('\r\n')
            while all_lines:
                length = int('0x' + all_lines.pop(0), 16)
                if length == 0:
                    break
                payload += all_lines.pop(0)
        else:
            payload = parsed_response.get_payload()

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


class AurTaskWorkerSearch(AurTaskWorker):

    def __init__(self, search_query):
        params = urlencode({
            'v': 5,
            'type': 'search',
            'arg': search_query,
            'by': 'name-desc'
        })
        self.uri = f'/rpc/?{params}'


class AurTaskWorkerInfo(AurTaskWorker):

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
        AurTaskWorkerInfo(packages=package_names)
    ).execute()
    json_results = result.json['results']
    found_aur_packages = [
        result['Name'] for result in json_results
    ]
    not_found_packages = []
    if len(package_names) != len(found_aur_packages):
        not_found_packages = [
            package for package in package_names
            if package not in found_aur_packages
        ]
        print("{} {}".format(
            color_line(':: warning:', 11),
            color_line('Following packages can not be found in AUR:', 15),
        ))
        for package in not_found_packages:
            print(format_paragraph(package))
    return json_results, not_found_packages


def find_aur_deps(package_names):

    def _get_deps(result):
        return [
            dep.split('=')[0].split('<')[0].split('>')[0] for dep in
            result.get('Depends', []) + result.get('MakeDepends', [])
        ]

    new_aur_deps = []
    while package_names:

        all_deps_for_aur_packages = []
        aur_pkgs_info, not_found_aur_pkgs = find_aur_packages(package_names)
        if not_found_aur_pkgs:
            sys.exit(1)
        for result in aur_pkgs_info:
            all_deps_for_aur_packages += _get_deps(result)
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
                aur_deps_info, not_found_aur_deps = find_aur_packages(
                    aur_deps_for_aur_packages
                )
                if not_found_aur_deps:
                    problem_package_names = []
                    for result in aur_pkgs_info:
                        deps = _get_deps(result)
                        for not_found_pkg in not_found_aur_deps:
                            if not_found_pkg in deps:
                                problem_package_names.append(result['Name'])
                                break
                    print("{} {}".format(
                        color_line(':: error:', 9),
                        color_line(
                            'Dependencies missing for '
                            f'{problem_package_names}',
                            15
                        ),
                    ))
                    sys.exit(1)
        new_aur_deps += aur_deps_for_aur_packages
        package_names = aur_deps_for_aur_packages

    return new_aur_deps


class TypeContainer():

    def __init__(self, **kwargs):
        not_found_atom = object()
        for key, value in kwargs.items():
            if getattr(self, key, not_found_atom) is not_found_atom:
                raise TypeError(
                    f"'{self.__class__.__name__}' does "
                    f"not have attribute '{key}'"
                )
            setattr(self, key, value)


class AurUpdate(TypeContainer):
    pkg_name = None
    current_version = None
    aur_version = None

    def pretty_format(self):
        return '{} {} -> {}'.format(
            color_line(self.pkg_name, 15),
            color_line(self.current_version, 10),
            color_line(self.aur_version, 10)
        )


def compare_versions(current_version, new_version):
    if current_version != new_version:
        current_base_version = new_base_version = None
        if ':' in current_version:
            current_base_version, current_version = current_version.split(':')
        if ':' in new_version:
            new_base_version, new_version = new_version.split(':')
        if (
            current_base_version and new_base_version
        ) and (
            current_base_version != new_base_version
        ):
            current_version = current_base_version
            new_version = new_base_version

        versions = [current_version, new_version]
        try:
            versions.sort(key=LooseVersion)
        except TypeError:
            return False
        return versions[1] == new_version
    return False


def find_aur_updates(package_versions):
    aur_pkgs_info, _not_found_aur_pkgs = find_aur_packages(
        package_versions.keys()
    )
    aur_updates = []
    for result in aur_pkgs_info:
        pkg_name = result['Name']
        aur_version = result['Version']
        current_version = package_versions[pkg_name]
        if compare_versions(current_version, aur_version):
            aur_update = AurUpdate(
                pkg_name=pkg_name,
                aur_version=aur_version,
                current_version=current_version,
            )
            aur_updates.append(aur_update)
    return aur_updates


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
    return None


class SrcInfo():

    lines = None

    def __init__(self, repo_path):
        with open(
            os.path.join(
                repo_path,
                '.SRCINFO'
            )
        ) as srcinfo_file:
            self.lines = srcinfo_file.readlines()

    def get_values(self, field):
        prefix = field + ' = '
        values = []
        for line in self.lines:
            if line.strip().startswith(prefix):
                values.append(line.strip().split(prefix)[1])
        return values

    def get_install_script(self):
        values = self.get_values('install')
        if values:
            return values[0]

    def get_makedepends(self):
        return self.get_values('makedepends')


def cli_install_packages(args, noconfirm=None, packages=None):
    if noconfirm is None:
        noconfirm = args.noconfirm
    # @TODO: split into smaller routines
    print("resolving dependencies...")
    packages = packages or args._positional
    if args.ignore:
        for ignored_pkg in args.ignore:
            packages.remove(ignored_pkg)
    pacman_packages, aur_packages = find_repo_packages(packages)
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

    if not noconfirm:
        answer = input('{} {}'.format(
            color_line('::', 12),
            color_line('Proceed with installation? [Y/n] ', 15),
        ))
        if answer:
            if answer.lower()[0] != 'y':
                sys.exit(1)

    all_aur_package_names = aur_packages + new_aur_deps
    repos_statuses = None
    if all_aur_package_names:
        repos_statuses = clone_git_repos(all_aur_package_names)

    # review PKGBUILD and install files
    # @TODO: ask about package conflicts/provides
    local_packages_found, _ = find_local_packages(
        all_aur_package_names
    )
    for pkg_name in reversed(all_aur_package_names):
        repo_status = repos_statuses[pkg_name]
        repo_path = repo_status.repo_path

        last_installed_file_path = os.path.join(
            repo_path,
            'last_installed.txt'
        )
        already_installed = False
        if (
                pkg_name in local_packages_found
        ) and (
            os.path.exists(last_installed_file_path)
        ):
            with open(last_installed_file_path) as last_installed_file:
                last_installed_hash = last_installed_file.readlines()
                with open(
                    os.path.join(
                        repo_path,
                        '.git/refs/heads/master'
                    )
                ) as current_hash_file:
                    current_hash = current_hash_file.readlines()
                    if last_installed_hash == current_hash:
                        already_installed = True
        repo_status.already_installed = already_installed

        if not ('--needed' in args._raw and already_installed):
            editor = get_editor()
            if editor:
                if ask_to_continue(
                        "Do you want to edit PKGBUILD for {} package?".format(
                            color_line(pkg_name, 15)
                        ),
                        default_yes=False
                ):
                    interactive_spawn([
                        get_editor(),
                        os.path.join(
                            repo_path,
                            'PKGBUILD'
                        )
                    ])

                install_file_name = SrcInfo(repo_path).get_install_script()
                if install_file_name:
                    if ask_to_continue(
                            "Do you want to edit {} for {} package?".format(
                                install_file_name,
                                color_line(pkg_name, 15)
                            ),
                            default_yes=False
                    ):
                        interactive_spawn([
                            get_editor(),
                            os.path.join(
                                repo_path,
                                install_file_name
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

        if '--needed' in args._raw and repo_status.already_installed:
            continue
        repo_path = repo_status.repo_path
        build_dir = os.path.join(BUILD_CACHE, pkg_name)
        if os.path.exists(build_dir):
            try:
                shutil.rmtree(build_dir)
            except PermissionError:
                interactive_spawn(['rm', '-rf', build_dir])
        shutil.copytree(repo_path, build_dir)

        # @TODO: args._unknown_args
        make_deps = SrcInfo(repo_path).get_makedepends()
        _, new_make_deps_to_install = find_local_packages(make_deps)
        if new_make_deps_to_install:
            interactive_spawn(
                [
                    'sudo',
                    'pacman',
                    '-S',
                    '--asdeps',
                    '--noconfirm',
                ] + args._unknown_args +
                new_make_deps_to_install,
            )
        build_result = interactive_spawn(
            [
                'makepkg',
                # '-rsf', '--noconfirm',
                '--nodeps',
            ],
            cwd=build_dir
        )
        if new_make_deps_to_install:
            interactive_spawn(
                [
                    'sudo',
                    'pacman',
                    '-Rs',
                    '--noconfirm',
                ] + new_make_deps_to_install,
            )
        if build_result.returncode > 0:
            print(color_line(f"Can't build '{pkg_name}'.", 9))
            if not ask_to_continue():
                sys.exit(1)
        else:
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
            ] + args._unknown_args +
            pacman_packages,
        )

    if args.downloadonly:
        return

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
            ] + args._unknown_args +
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
            ] + args._unknown_args +
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


def pretty_print_upgradeable(packages_updates):
    print('\n'.join([
        format_paragraph(pkg_update.pretty_format())
        for pkg_update in packages_updates
    ]))


def print_upgradeable(packages_updates):
    print('\n'.join([
        pkg_update.pkg_name
        for pkg_update in packages_updates
    ]))


def cli_print_upgradeable(args):
    updates = find_repo_updates()
    updates += find_aur_updates(find_packages_not_from_repo())
    updates = sorted(updates, key=lambda u: u.pkg_name)
    if args.quiet:
        print_upgradeable(updates)
    else:
        pretty_print_upgradeable(updates)


def cli_upgrade_packages(args):
    if args.refresh:
        interactive_spawn(['sudo', 'pacman', '-Sy'])

    print('{} {}'.format(
        color_line('::', 12),
        color_line('Starting full system upgrade...', 15)
    ))
    repo_packages_updates = find_repo_updates()
    pretty_print_upgradeable(repo_packages_updates)

    print('\n{} {}'.format(
        color_line('::', 12),
        color_line('Starting full AUR upgrade...', 15)
    ))
    aur_updates = find_aur_updates(find_packages_not_from_repo())

    print('\n{} {}'.format(
        color_line('::', 12),
        color_line('AUR packages updates:', 15)
    ))
    pretty_print_upgradeable(aur_updates)

    print()
    answer = input('{} {}\n{} {}\n> '.format(
        color_line('::', 12),
        color_line('Proceed with installation? [Y/n] ', 15),
        color_line('::', 12),
        color_line('[V]iew package detail   [M]anually select packages', 15)
    ))
    if answer:
        if answer.lower()[0] != 'y':
            sys.exit(1)
    return cli_install_packages(
        args=args,
        packages=[u.pkg_name for u in repo_packages_updates] +
        [u.pkg_name for u in aur_updates]
    )


def cli_info_packages(_args):
    # @TODO:
    raise NotImplementedError()


def cli_clean_packages_cache(_args):
    # @TODO:
    print(_args)
    raise NotImplementedError()


def cli_search_packages(args):
    pkgs = 'pkgs'
    aur = 'aur'
    result = MultipleTasksExecutor({
        pkgs: PacmanColorTaskWorker(args._raw),
        aur: AurTaskWorkerSearch(
            search_query=' '.join(args._positional or [])
        ),
    }).execute()

    print(result[pkgs].stdout, end='')
    for aur_pkg in result[aur].json['results']:
        if args.quiet:
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


def cli_version():
        sys.stdout.buffer.write("""
      /:}               _
     /--1             / :}
    /   |           / `-/
   |  ,  --------  /   /
   |'                 Y
  /                   l     Pikaur v0.1
  l  /       \        l     (C) 2018 Pikaur development team
  j  ●   .   ●        l     Licensed under GPLv3
 { )  ._,.__,   , -.  {
  У    \  _/     ._/   \\

""".encode())


def parse_args(args):
    parser = argparse.ArgumentParser(prog=sys.argv[0], add_help=False)
    for letter, opt in (
        ('S', 'sync'),
        ('w', 'downloadonly'),
        ('q', 'quiet'),
        ('h', 'help'),
        ('u', 'sysupgrade'),
        ('y', 'refresh'),
        #
        ('Q', 'query'),
        ('V', 'version'),
    ):
        parser.add_argument('-'+letter, '--'+opt, action='store_true')
    for opt in (
        'noconfirm',
    ):
        parser.add_argument('--'+opt, action='store_true')
    for letter in (
        'b', 'c', 'd', 'g', 'i', 'l', 'p', 'r', 's', 'v',
    ):
        parser.add_argument('-'+letter, action='store_true')
    parser.add_argument('_positional', nargs='*')
    parser.add_argument('--ignore', action='append')

    parsed_args, unknown_args = parser.parse_known_args(args)
    parsed_args._unknown_args = unknown_args
    parsed_args._raw = args

    # print(f'args = {args}')
    # print("ARGPARSE:")
    reconstructed_args = {
        key: value
        for key, value in parsed_args.__dict__.items()
        if not key.startswith('_')
    }
    print(reconstructed_args)
    # print(unknown_args)
    # sys.exit(0)

    return parsed_args


def main():
    raw_args = sys.argv[1:]
    args = parse_args(raw_args)

    if args.help:
        return interactive_spawn(['pacman', ] + raw_args)
    elif args.sync:
        if args.sysupgrade:
            return cli_upgrade_packages(args)
        elif args.s:
            return cli_search_packages(args)
        elif args.i:
            return cli_info_packages(args)
        elif args.c:
            return cli_clean_packages_cache(args)
        elif '-S' in raw_args:
            return cli_install_packages(args)
    elif args.query:
        if args.sysupgrade:
            return cli_print_upgradeable(args)
    elif args.version:
        return cli_version()

    return interactive_spawn(['sudo', 'pacman', ] + raw_args)


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
