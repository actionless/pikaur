# noqa: INP001
"""
PyALPM compatibility interface for PypyALPM.
To be used with apps depending on pyalpm with pypyalpm.
"""
from typing import Final

import pypyalpm

DB = pypyalpm.DB  # nonfinal-ignore
Package = pypyalpm.Package  # nonfinal-ignore
vercmp = pypyalpm.compare_versions  # nonfinal-ignore


LOG_ERROR: Final = True
LOG_WARNING: Final = True


def version() -> str:
    return "-pypy-0.0.1"


class Handle(pypyalpm.Handle):

    # def __init__(self, root_dir: str, db_path: str) -> None:
    #     self.root_dir = root_dir
    #     self.db_path = db_path

    def register_syncdb(self, repo: str, flag: int) -> DB:
        return DB(name=repo, handle=self, flag=flag)

    def get_localdb(self) -> DB:
        return DB(name=pypyalpm.DB_NAME_LOCAL, handle=self)

    def get_syncdbs(self) -> list[DB]:
        return [
            DB(name=db_name, handle=self)
            for db_name in pypyalpm.PackageDB.get_db_names(handle=self)
        ]
