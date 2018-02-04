import os
import gzip
import tempfile
import shutil
from pprint import pformat

from .core import (
    DataType,
    CmdTaskWorker, MultipleTasksExecutor,
    get_package_name_from_depend_line,
)


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


PACMAN_LIST_FIELDS = (
    'Conflicts_With',
    'Replaces',
    'Depends_On',
    'Provides',
    'Required_By',
    'Optional_For',
)


PACMAN_DICT_FIELDS = (
    'Optional_Deps',
)


DB_INFO_TRANSLATION = {
    '%NAME%': 'Name',
    '%VERSION%': 'Version',
    '%PROVIDES%': 'Provides',
    '%DESC%': 'Description',
    '%CONFLICTS%': 'Conflicts_With',
}


class PacmanPackageInfo(DataType):
    Name = None
    Version = None
    Description = None
    Architecture = None
    URL = None
    Licenses = None
    Groups = None
    Provides = None
    Depends_On = None
    Optional_Deps = None
    Conflicts_With = None
    Replaces = None
    Installed_Size = None
    Packager = None
    Build_Date = None
    Validated_By = None

    def __repr__(self):
        return f'<{self.__class__.__name__} "{self.Name}">'

    @property
    def all(self):
        return pformat(self.__dict__)

    @classmethod
    def parse_pacman_cli_info(cls, lines):
        pkg = cls()
        field = value = None
        for line in lines:
            if line == '':
                yield pkg
                pkg = cls()
                continue
            if not line.startswith(' '):
                try:
                    _field, _value, *_args = line.split(': ')
                except ValueError as exc:
                    print(line)
                    print(field, value)
                    raise exc
                field = _field.rstrip().replace(' ', '_')
                if _value == 'None':
                    value = None
                else:
                    if field in PACMAN_DICT_FIELDS:
                        value = {_value: None}
                    elif field in PACMAN_LIST_FIELDS:
                        value = _value.split()
                    else:
                        value = _value
                    if _args:
                        if field in PACMAN_DICT_FIELDS:
                            value = {_value: _args[0]}
                        else:
                            value = ': '.join([_value] + _args)
                            if field in PACMAN_LIST_FIELDS:
                                value = value.split()
            else:
                if field in PACMAN_DICT_FIELDS:
                    _value, *_args = line.split(': ')
                    # pylint: disable=unsupported-assignment-operation
                    value[_value] = _args[0] if _args else None
                elif field in PACMAN_LIST_FIELDS:
                    value += line.split()
                else:
                    value += line

            try:
                setattr(pkg, field, value)
            except TypeError as exc:
                print(line)
                raise exc

    @classmethod
    def _parse_pacman_db_info(cls, db_file_name, open_method):

        def verbose_setattr(pkg, real_field, value):
            try:
                setattr(pkg, real_field, value)
            except TypeError as exc:
                print(line)
                raise exc

        with open_method(db_file_name) as db_file:
            pkg = cls()
            line = field = real_field = value = None
            while line != '':
                line = db_file.readline().decode('utf-8')
                if line.startswith('%'):

                    if field in DB_INFO_TRANSLATION:
                        verbose_setattr(pkg, real_field, value)

                    field = line.strip()
                    real_field = DB_INFO_TRANSLATION.get(field)
                    if not real_field:
                        continue

                    if real_field == 'Name' and pkg.Name:
                        yield pkg
                        pkg = cls()

                    if real_field in PACMAN_LIST_FIELDS:
                        value = []
                    elif real_field in PACMAN_DICT_FIELDS:
                        value = {}
                    else:
                        value = ''
                else:
                    if field not in DB_INFO_TRANSLATION:
                        continue

                    _value = line.strip()
                    if real_field in PACMAN_LIST_FIELDS:
                        value.append(_value)
                    elif real_field in PACMAN_DICT_FIELDS:
                        subkey, *subvalue = _value.split(': ')
                        subvalue = ': '.join(*subvalue)
                        # pylint: disable=unsupported-assignment-operation
                        value[subkey] = subvalue
                    else:
                        value += _value

            if field in DB_INFO_TRANSLATION:
                verbose_setattr(pkg, real_field, value)
            yield pkg

    @classmethod
    def parse_pacman_db_gzip_info(cls, file_name):
        return cls._parse_pacman_db_info(file_name, gzip.open)

    @classmethod
    def parse_pacman_db_info(cls, file_name):
        return cls._parse_pacman_db_info(file_name, lambda x: open(x, 'rb'))


class RepoPackageInfo(PacmanPackageInfo):
    Repository = None
    Download_Size = None


class LocalPackageInfo(PacmanPackageInfo):
    Required_By = None
    Optional_For = None
    Install_Date = None
    Install_Reason = None
    Install_Script = None


class PackageDBCommon():

    _repo_cache = None
    _local_cache = None
    _repo_dict_cache = None
    _local_dict_cache = None
    _repo_provided_cache = None
    _local_provided_cache = None

    repo = 'repo'
    local = 'local'

    @classmethod
    def get_repo_list(cls):
        if not cls._repo_cache:
            cls._repo_cache = cls.get_repo_dict().values()
        return cls._repo_cache

    @classmethod
    def get_local_list(cls):
        if not cls._local_cache:
            cls._local_cache = cls.get_local_dict().values()
        return cls._local_cache

    @classmethod
    def get_repo_dict(cls):
        if not cls._repo_dict_cache:
            cls._repo_dict_cache = {
                pkg.Name: pkg
                for pkg in cls.get_repo_list()
            }
        return cls._repo_dict_cache

    @classmethod
    def get_local_dict(cls):
        if not cls._local_dict_cache:
            cls._local_dict_cache = {
                pkg.Name: pkg
                for pkg in cls.get_local_list()
            }
        return cls._local_dict_cache

    @classmethod
    def _get_provided(cls, local):
        provided_pkg_names = []
        for pkg in (
                cls.get_local_list() if local == cls.local
                else cls.get_repo_list()
        ):
            if pkg.Provides:
                for provided_pkg in pkg.Provides:
                    provided_pkg_names.append(
                        get_package_name_from_depend_line(provided_pkg)
                    )
        return provided_pkg_names

    @classmethod
    def get_repo_provided(cls):
        if not cls._repo_provided_cache:
            cls._repo_provided_cache = cls._get_provided(cls.repo)
        return cls._repo_provided_cache

    @classmethod
    def get_local_provided(cls):
        if not cls._local_provided_cache:
            cls._local_provided_cache = cls._get_provided(cls.local)
        return cls._local_provided_cache


class PackageDB_ALPM9(PackageDBCommon):

    # ~2.2 seconds

    @classmethod
    def get_repo_dict(cls):
        if not cls._repo_dict_cache:
            print("Reading repository package databases...")
            result = {}
            temp_dir = tempfile.mkdtemp()
            sync_dir = '/var/lib/pacman/sync/'

            # copy repos dbs to temp location
            temp_repos = {}
            for repo_name in os.listdir(sync_dir):
                if not repo_name.endswith('.db'):
                    continue
                temp_repo_path = os.path.join(temp_dir, repo_name+'.gz')
                shutil.copy2(
                    os.path.join(sync_dir, repo_name),
                    temp_repo_path,
                )
                temp_repos[repo_name] = temp_repo_path

            # uncompress databases
            MultipleTasksExecutor({
                repo_name: CmdTaskWorker([
                    'gunzip', temp_repo_path
                ])
                for repo_name, temp_repo_path
                in temp_repos.items()
            }).execute()

            # parse package databases
            for repo_name in temp_repos:
                for pkg in RepoPackageInfo.parse_pacman_db_info(
                        os.path.join(temp_dir, repo_name)
                ):
                    result[pkg.Name] = pkg
            shutil.rmtree(temp_dir)
            cls._repo_dict_cache = result
        return cls._repo_dict_cache

    @classmethod
    def get_local_dict(cls):
        if not cls._local_dict_cache:
            print("Reading local package database...")
            result = {}
            local_dir = '/var/lib/pacman/local/'
            for pkg_dir_name in os.listdir(local_dir):
                if not os.path.isdir(os.path.join(local_dir, pkg_dir_name)):
                    continue
                for pkg in LocalPackageInfo.parse_pacman_db_info(
                        os.path.join(local_dir, pkg_dir_name, 'desc')
                ):
                    result[pkg.Name] = pkg
            cls._local_dict_cache = result
        return cls._local_dict_cache


class PackageDB_ALPM9_PurePython(PackageDB_ALPM9):

    # ~3.7 seconds

    @classmethod
    def get_repo_dict(cls):
        if not cls._repo_dict_cache:
            result = {}
            sync_dir = '/var/lib/pacman/sync/'
            for repo_name in os.listdir(sync_dir):
                if not repo_name.endswith('.db'):
                    continue
                print(f"Reading {repo_name} repository data...")
                for pkg in RepoPackageInfo.parse_pacman_db_gzip_info(
                        os.path.join(sync_dir, repo_name)
                ):
                    result[pkg.Name] = pkg
            cls._repo_dict_cache = result
        return cls._repo_dict_cache


class PackageDbCli(PackageDBCommon):

    # ~4.7 seconds

    @classmethod
    def _get_dbs(cls):
        if not cls._repo_cache:
            print("Retrieving local pacman database...")
            results = MultipleTasksExecutor({
                cls.repo: PacmanTaskWorker(['-Si', ]),
                cls.local: PacmanTaskWorker(['-Qi', ]),
            }).execute()
            cls._repo_cache = list(RepoPackageInfo.parse_pacman_cli_info(
                results[cls.repo].stdouts
            ))
            cls._local_cache = list(LocalPackageInfo.parse_pacman_cli_info(
                results[cls.local].stdouts
            ))
        return {
            cls.repo: cls._repo_cache,
            cls.local: cls._local_cache
        }

    @classmethod
    def get_repo_list(cls):
        return cls._get_dbs()[cls.repo]

    @classmethod
    def get_local_list(cls):
        return cls._get_dbs()[cls.local]


with open('/var/lib/pacman/local/ALPM_DB_VERSION') as version_file:
    ALPM_DB_VER = version_file.read().strip()
    if ALPM_DB_VER == '9':
        if os.path.exists('/usr/bin/gunzip'):
            PackageDB = PackageDB_ALPM9
        else:
            PackageDB = PackageDB_ALPM9_PurePython
    else:
        PackageDB = PackageDbCli


def find_pacman_packages(packages, local=False):
    all_repo_packages = (
        PackageDB.get_local_dict() if local else PackageDB.get_repo_dict()
    ).keys()
    pacman_packages = []
    not_found_packages = []
    for package_name in packages:
        if package_name in all_repo_packages:
            pacman_packages.append(package_name)
        else:
            not_found_packages.append(package_name)
    return pacman_packages, not_found_packages


def find_repo_packages(packages):
    return find_pacman_packages(packages, local=False)


def find_local_packages(packages):
    return find_pacman_packages(packages, local=True)


def find_packages_not_from_repo():
    _repo_packages, not_found_packages = find_repo_packages(
        PackageDB.get_local_dict().keys()
    )
    return {
        pkg_name: PackageDB.get_local_dict()[pkg_name].Version
        for pkg_name in not_found_packages
    }
