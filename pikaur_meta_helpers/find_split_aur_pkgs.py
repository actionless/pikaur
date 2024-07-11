from pikaur_meta_helpers.util import load_aur_dump


def main() -> None:
    aur_pkgs = load_aur_dump()

    print("Filtering...\n")
    pkgbases: dict[str, list[str]] = {}
    for pkg in aur_pkgs:
        pkgbases.setdefault(pkg.packagebase, []).append(pkg.name)

    # Print all split-packages:
    for pkgbase, pkgnames in pkgbases.items():
        if len(pkgnames) > 1:
            print(f"{pkgbase}: {pkgnames}")


if __name__ == "__main__":
    main()
