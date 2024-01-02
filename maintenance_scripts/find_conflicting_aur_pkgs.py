import pickle  # nosec B403
import sys
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
