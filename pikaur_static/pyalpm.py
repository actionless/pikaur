"""
PyALPM compatibility interface for PypyALPM.
To be used with apps depending on pyalpm with pypyalpm.
"""
from typing import Final

import pypyalpm

DB = pypyalpm.DB
Package = pypyalpm.Package
vercmp = pypyalpm.compare_versions


LOG_ERROR: Final = True
LOG_WARNING: Final = True


def version() -> str:
    return "-pypy-0.0.1"


class Handle:

    @staticmethod
    def get_localdb() -> DB:
        return DB(pypyalpm.DB_NAME_LOCAL)

    @staticmethod
    def get_syncdbs() -> list[DB]:
        return [
            DB(name=db_name)
            for db_name in pypyalpm.PackageDB.get_dbs()  # pylint: disable=not-an-iterable
        ]

    def __init__(self, root_dir: str, db_path: str) -> None:
        pass

    @staticmethod
    def register_syncdb(repo: str, flag: int) -> DB:  # pylint: disable=unused-argument  # noqa: ARG004,E501,RUF100
        return DB(name=repo)
