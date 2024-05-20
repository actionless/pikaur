import pickle  # nosec B403
from pathlib import Path

import tqdm  # type: ignore[import-untyped]

from pikaur.aur import get_all_aur_packages
from pikaur.pacman import PackageDB

# from pikaur.progressbar import ProgressBar
from pikaur.version import VersionMatcher

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
all_aur_pkgnames = [pkg.name for pkg in aur_pkgs]
all_local_pkgs = PackageDB.get_local_dict()
matching_packages: dict[str, list[VersionMatcher]] = {}
print("starting...")
# with ProgressBar(len(aur_pkgs), "progress") as update:
# for pkg in aur_pkgs:
for pkg in tqdm.tqdm(aur_pkgs):
    for dep_name in pkg.depends:
        dep = VersionMatcher(dep_name)
        if (dep.pkg_name in all_aur_pkgnames) and ((">" in dep_name) or ("<" in dep_name)):
            matching_packages.setdefault(pkg.name, []).append(dep)

for pkg_name, deps in matching_packages.items():
    dep_names = (dep.pkg_name for dep in deps)
    if len(deps) != len(set(dep_names)):
        print(pkg_name, deps)
