import sys

from pikaur_meta_helpers.util import load_aur_dump


def main() -> None:
    aur_pkgs = load_aur_dump()

    print("Filtering...\n")
    all_conflicts: dict[str, list[str]] = {}
    for pkg in aur_pkgs:
        for name in [pkg.name]:  # + list(getattr(pkg, "provides", [])):
            for conf in getattr(pkg, "conflicts", []):
                all_conflicts.setdefault(name, []).append(conf)

    # Print all conflicting packages in AUR:
    try:
        for pkgbase in all_conflicts:
            for pkgbase_2, pkgnames_2 in all_conflicts.items():
                if pkgbase != pkgbase_2 and pkgbase in pkgnames_2:
                    print(f"{pkgbase}: {pkgbase_2}")
    except BrokenPipeError:
        sys.exit()


if __name__ == "__main__":
    main()
