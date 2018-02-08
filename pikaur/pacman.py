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
from .pprint import color_line


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
                    if _value == '':
                        continue
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
    def _get_provided_dict(cls, local):
        provided_pkg_names = {}
        for pkg in (
                cls.get_local_list() if local == cls.local
                else cls.get_repo_list()
        ):
            if pkg.Provides:
                for provided_pkg in pkg.Provides:
                    provided_pkg_names.setdefault(pkg.Name, []).append(
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

    @classmethod
    def get_repo_provided_dict(cls):
        if not cls._repo_provided_cache:
            cls._repo_provided_cache = cls._get_provided_dict(cls.repo)
        return cls._repo_provided_cache

    @classmethod
    def get_local_provided_dict(cls):
        if not cls._local_provided_cache:
            cls._local_provided_cache = cls._get_provided_dict(cls.local)
        return cls._local_provided_cache


class PackageDB_ALPM9(PackageDBCommon):  # pylint: disable=invalid-name

    # ~2.7 seconds (was ~2.2 seconds with gzip)

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
                temp_repo_path = os.path.join(temp_dir, repo_name)
                shutil.copy2(
                    os.path.join(sync_dir, repo_name),
                    temp_repo_path,
                )
                temp_repos[repo_name] = temp_repo_path

            # uncompress databases
            untar_results = MultipleTasksExecutor({
                repo_name: CmdTaskWorker([
                    'bsdtar', '-x', '-f', temp_repo_path, '-C', temp_dir
                ])
                for repo_name, temp_repo_path
                in temp_repos.items()
            }).execute()
            for db_name, untar_result in untar_results.items():
                if untar_result.return_code != 0:
                    print('{} Can not extract {}, skipping'.format(
                        color_line(':: error', 9),
                        db_name
                    ))
                    print(untar_result)
            for temp_repo_path in temp_repos.values():
                os.remove(temp_repo_path)

            # parse package databases
            # @TODO: try multiprocess pool here
            for pkg_dir_name in os.listdir(temp_dir):
                if not os.path.isdir(os.path.join(temp_dir, pkg_dir_name)):
                    continue
                db_dir = os.path.join(temp_dir, pkg_dir_name)
                for pkg in LocalPackageInfo.parse_pacman_db_info(
                    os.path.join(db_dir, 'desc')
                ):
                    result[pkg.Name] = pkg
                shutil.rmtree(db_dir)

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


with open('/var/lib/pacman/local/ALPM_DB_VERSION') as version_file:
    ALPM_DB_VER = version_file.read().strip()
    if ALPM_DB_VER == '9':
        PackageDB = PackageDB_ALPM9
    else:
        from .pacman_fallback import get_pacman_cli_package_db
        PackageDB = get_pacman_cli_package_db(
            PackageDBCommon=PackageDBCommon,
            RepoPackageInfo=RepoPackageInfo,
            LocalPackageInfo=LocalPackageInfo,
            PacmanTaskWorker=PacmanTaskWorker,
            PACMAN_DICT_FIELDS=PACMAN_DICT_FIELDS,
            PACMAN_LIST_FIELDS=PACMAN_LIST_FIELDS
        )


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
