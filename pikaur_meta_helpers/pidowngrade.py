"""
A POC for downgrade interface in future Pikaur versions.
Or so.
"""

import sys

from pikaur.pacman import PackageDB
from pikaur_test.helpers import PikaurDbTestCase

# BUILD_ROOT = "/tmp/"


def print_usage() -> None:
    print(f"Usage: {sys.argv[0]} PKG_NAME VERSION")


def main() -> None:
    print(sys.argv)
    min_args = 2

    if len(sys.argv) < min_args:
        print_usage()
        sys.exit(1)
    pkg_name = sys.argv[1]
    version = sys.argv[2]

    pkg_db = PackageDB()
    worker = PikaurDbTestCase()
    if pkg_name in pkg_db.get_repo_pkgnames():
        worker.downgrade_repo_pkg(
            pkg_name,
            # build_root=BUILD_ROOT,  # @TODO: fixme
            remove_before_upgrade=False,
            to_version=version,
        )
    else:
        worker.downgrade_aur_pkg(pkg_name)


if __name__ == "__main__":
    main()
