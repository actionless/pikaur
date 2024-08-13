

def vercmp(x: str, y: str) -> int: ...

def version() -> str: ...

class DB:
    name: str
    def search(self, query: str) -> list[Package]: ...
    def get_pkg(self, name: str) -> Package: ...

class Handle:
    def get_localdb(self) -> DB: ...
    def get_syncdbs(self) -> list[DB]: ...

class Package:
    db: DB
    # description properties
    name: str
    version: str
    desc: str
    url: str
    arch: str
    licenses: list[str]
    groups: list[str]
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
    depends: list[str]
    optdepends: list[str]
    conflicts: list[str]
    provides: list[str]
    replaces: list[str]
  # /* miscellaneous information */
  # { "has_scriptlet", (getter)pyalpm_pkg_has_scriptlet, 0, "True if the package has an install script", NULL },
  # { "download_size", (getter)pyalpm_pkg_download_size, 0, "predicted download size for this package", NULL },
    def compute_requiredby(self) -> list[str]: ...
    def compute_optionalfor(self) -> list[str]: ...

# vim: ft=python
