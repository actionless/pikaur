from pikaur.pacman import PackageDB
from pikaur_meta_helpers.util import load_aur_dump


def main() -> None:
    aur_pkgs = load_aur_dump()
    print("Filtering...\n")
    all_repo_pkgnames = PackageDB.get_repo_pkgnames()
    all_local_pkgs = PackageDB.get_local_dict()
    matching_packages: dict[str, list[str]] = {}
    for pkg in aur_pkgs:
        for make_dep_name in pkg.makedepends:
            if (make_dep_name in all_repo_pkgnames) and (make_dep_name not in all_local_pkgs):
                matching_packages.setdefault(pkg.name, []).append(make_dep_name)

    print(matching_packages)


if __name__ == "__main__":
    main()
