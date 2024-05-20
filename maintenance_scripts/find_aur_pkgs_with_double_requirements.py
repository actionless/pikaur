import pickle  # nosec B403
from pathlib import Path
from typing import TypedDict

import tqdm  # type: ignore[import-untyped]

from pikaur.aur import get_all_aur_packages
from pikaur.version import VersionMatcher


class Item(TypedDict):
    deps: list[VersionMatcher]
    counter: int


PICKLE_FILE = Path("aur_db.dump")


if PICKLE_FILE.exists():
    print(f"Opening db dump '{PICKLE_FILE}'...")
    with PICKLE_FILE.open("rb") as fobj_read:
        aur_pkgs = pickle.load(fobj_read)  # nosec B301
else:
    print("Fetching...")
    aur_pkgs = get_all_aur_packages()
    print(f"Saving db dump to '{PICKLE_FILE}'...")
    with PICKLE_FILE.open("wb") as fobj_write:
        pickle.dump(aur_pkgs, fobj_write)

all_aur_pkgnames = [pkg.name for pkg in aur_pkgs]
matching_packages: dict[str, Item] = {}
print("Filtering...")
for pkg in tqdm.tqdm(aur_pkgs):
    for dep_name in pkg.depends:
        dep = VersionMatcher(dep_name)
        if (dep.pkg_name in all_aur_pkgnames) and ((">" in dep_name) or ("<" in dep_name)):
            matching_packages.setdefault(
                pkg.name, {"deps": [], "counter": 0},
            ).setdefault("deps", []).append(dep)
            matching_packages[pkg.name]["counter"] = len(pkg.depends) + len(pkg.makedepends)

for pkg_name, item in sorted(matching_packages.items(), key=lambda x: x[1]["counter"]):
    deps = item["deps"]
    dep_names = (dep.pkg_name for dep in deps)
    if len(deps) != len(set(dep_names)):
        print(item["counter"], pkg_name, deps)
