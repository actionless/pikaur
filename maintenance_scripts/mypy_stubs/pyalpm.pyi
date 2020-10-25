from typing import List


def vercmp(x: str, y: str) -> int: ...

def version() -> str: ...

class DB:
    name: str
    def search(self, query: str) -> List["Package"]: ...


class Handle:
    def get_localdb(self) -> DB: ...
    def get_syncdbs(self) -> List[DB]: ...


class Package:
    db: DB
    # description properties
    name: str
    version: str
    desc: str
    url: str
    arch: str
    licenses: List[str]
    groups: List[str]
    # package properties
    packager: str
    md5sum: str
    sha256sum: str
    base64_sig: str
    filename: str
    base: str
    size: int
    isize: int
    reason: int
    builddate: int
    installdate: int
  # { "files",  (getter)pyalpm_package_get_files, 0, "list of installed files", NULL } ,
  # { "backup", (getter)_get_list_attribute, 0, "list of tuples (filename, md5sum)", &get_backup } ,
  # { "deltas", (getter)_get_list_attribute, 0, "list of available deltas", &get_deltas } ,
  # /* dependency information */
    depends: List[str]
    optdepends: List[str]
    conflicts: List[str]
    provides: List[str]
    replaces: List[str]
  # /* miscellaneous information */
  # { "has_scriptlet", (getter)pyalpm_pkg_has_scriptlet, 0, "True if the package has an install script", NULL },
  # { "download_size", (getter)pyalpm_pkg_download_size, 0, "predicted download size for this package", NULL },


# vim: ft=python
