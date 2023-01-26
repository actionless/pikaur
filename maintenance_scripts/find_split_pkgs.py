import pickle  # nosec B403
from pathlib import Path

from pikaur.aur import get_all_aur_packages

PICKLE_FILE = Path("aur_db.dump")


if PICKLE_FILE.exists():
    print(f"Opening db dump '{PICKLE_FILE}'...")
    with PICKLE_FILE.open("rb") as fobj:
        aur_pkgs = pickle.load(fobj)  # nosec B301
else:
    print("Fetching...")
    aur_pkgs = get_all_aur_packages()
    print(f"Saving db dump to '{PICKLE_FILE}'...")
    with PICKLE_FILE.open("wb") as fobj:
        pickle.dump(aur_pkgs, fobj)

print("Filtering...\n")
pkgbases: dict[str, list[str]] = {}
for pkg in aur_pkgs:
    pkgbases.setdefault(pkg.packagebase, []).append(pkg.name)

# Print all split-packages:
for pkgbase, pkgnames in pkgbases.items():
    if len(pkgnames) > 1:
        print(f"{pkgbase}: {pkgnames}")
