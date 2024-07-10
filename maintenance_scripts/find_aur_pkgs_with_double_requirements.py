import math
import os
import pickle  # nosec B403
from multiprocessing.pool import ThreadPool
from pathlib import Path
from typing import TypedDict

import tqdm  # type: ignore[import-untyped]

from pikaur.aur import AURPackageInfo, get_all_aur_packages
from pikaur.version import VersionMatcher


class Item(TypedDict):
    deps: list[VersionMatcher]
    counter: int


PICKLE_FILE = Path("aur_db.dump")


def load_aur_dump() -> list[AURPackageInfo]:
    aur_pkgs: list[AURPackageInfo]
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
    return aur_pkgs


def filter_thread(
        idx: int, aur_pkgs: list[AURPackageInfo], all_aur_pkgnames: dict[str, bool],
) -> dict[str, Item]:
    matching_packages: dict[str, Item] = {}
    for pkg in tqdm.tqdm(aur_pkgs, position=idx):
        for dep_name in pkg.depends:
            dep = VersionMatcher(dep_name)
            if (all_aur_pkgnames.get(dep.pkg_name)) and ((">" in dep_name) or ("<" in dep_name)):
                matching_packages.setdefault(
                    pkg.name, {"deps": [], "counter": 0},
                ).setdefault("deps", []).append(dep)
                matching_packages[pkg.name]["counter"] = len(pkg.depends) + len(pkg.makedepends)
    return matching_packages


def main() -> None:
    aur_pkgs = load_aur_dump()
    all_aur_pkgnames = {pkg.name: True for pkg in aur_pkgs}

    print("Filtering...")
    matching_packages: dict[str, Item] = {}
    nproc = len(os.sched_getaffinity(0))
    num_pkgs = len(aur_pkgs)
    pkgs_per_thread = math.ceil(num_pkgs / nproc)
    print(f"{num_pkgs=}")
    for proc_idx in range(nproc):
        print(
            (proc_idx, proc_idx * pkgs_per_thread, (proc_idx + 1) * pkgs_per_thread),
        )
    with ThreadPool() as pool:
        threads = [
            pool.apply_async(
                filter_thread,
                (
                    proc_idx,
                    aur_pkgs[proc_idx * pkgs_per_thread:(proc_idx + 1) * pkgs_per_thread],
                    all_aur_pkgnames,
                ),
            )
            for proc_idx in range(nproc)
        ]
        pool.close()
        pool.join()
        for thread in threads:
            matching_packages.update(thread.get())
    for _ in range(nproc):
        print()

    for pkg_name, item in sorted(matching_packages.items(), key=lambda x: x[1]["counter"]):
        deps = item["deps"]
        dep_names = (dep.pkg_name for dep in deps)
        if len(deps) != len(set(dep_names)):
            print(item["counter"], pkg_name, deps)


if __name__ == "__main__":
    main()
