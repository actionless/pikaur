from pprint import pprint
from typing import Final

from pikaur.pacman import PackageDB
from pikaur_meta_helpers.util import load_aur_dump

MAX_REPO_PKG_SIZE_KB: Final = 100


def main() -> None:
    aur_pkgs = load_aur_dump()
    all_repo_pkgnames = PackageDB.get_repo_pkgnames()
    all_repo_pkgs = {name.split("/")[1]: pkg for name, pkg in PackageDB.get_repo_dict().items()}
    print("Filtering...\n")
    all_conflicts: dict[str, list[str]] = {}
    for pkg in aur_pkgs:
        for name in [pkg.name]:  # + list(getattr(pkg, "provides", [])):
            for conf in getattr(pkg, "conflicts", []):
                if conf in all_repo_pkgnames:
                    repo_pkg = all_repo_pkgs[conf]
                    size_k = repo_pkg.size / 1024
                    if size_k < MAX_REPO_PKG_SIZE_KB:
                        all_conflicts.setdefault(conf, []).append(name)

    pprint(all_conflicts)


if __name__ == "__main__":
    main()
