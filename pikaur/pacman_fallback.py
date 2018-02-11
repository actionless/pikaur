from .core import MultipleTasksExecutor


def get_pacman_cli_package_db(
        PackageDBCommon, RepoPackageInfo, LocalPackageInfo, PacmanTaskWorker,
        PACMAN_DICT_FIELDS, PACMAN_LIST_FIELDS,
):  # pylint: disable=invalid-name,too-many-arguments

    class CliPackageInfo():

        @classmethod
        def parse_pacman_cli_info(cls, lines):
            # pylint: disable=too-many-nested-blocks,too-many-branches
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

    class CliRepoPackageInfo(RepoPackageInfo, CliPackageInfo):
        pass

    class CliLocalPackageInfo(LocalPackageInfo, CliPackageInfo):
        pass

    class PackageDbCli(PackageDBCommon):

        # ~4.7 seconds

        @classmethod
        def _get_dbs(cls):
            if not cls._packages_list_cache:
                print("Retrieving local pacman database...")
                results = MultipleTasksExecutor({
                    cls.repo: PacmanTaskWorker(['-Si', ]),
                    cls.local: PacmanTaskWorker(['-Qi', ]),
                }).execute()
                repo_cache = list(CliRepoPackageInfo.parse_pacman_cli_info(
                    results[cls.repo].stdouts
                ))
                local_cache = list(CliLocalPackageInfo.parse_pacman_cli_info(
                    results[cls.local].stdouts
                ))
                cls._packages_list_cache = {
                    cls.repo: repo_cache,
                    cls.local: local_cache
                }
            return cls._packages_list_cache

        @classmethod
        def get_repo_list(cls):
            return cls._get_dbs()[cls.repo]

        @classmethod
        def get_local_list(cls):
            return cls._get_dbs()[cls.local]

    return PackageDbCli
