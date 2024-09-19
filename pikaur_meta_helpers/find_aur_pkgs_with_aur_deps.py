import math
import os
from multiprocessing.pool import ThreadPool
from typing import Final, TypedDict

from pikaur.pikatypes import AURPackageInfo
from pikaur.version import VersionMatcher
from pikaur_meta_helpers.util import load_aur_dump

QUERY: Final = "python"
UNQUERY: Final = "python2"


class Item(TypedDict):
    deps: list[VersionMatcher]
    counter: int


def filter_thread(
        _idx: int, aur_pkgs: list[AURPackageInfo], all_aur_pkgnames: dict[str, bool],
) -> dict[str, Item]:
    matching_packages: dict[str, Item] = {}
    for pkg in aur_pkgs:
        if QUERY not in pkg.name:
            continue
        if UNQUERY in pkg.name:
            continue
        for dep_name in pkg.depends:
            if UNQUERY in dep_name:
                break
            dep = VersionMatcher(dep_name)
            if all_aur_pkgnames.get(dep.pkg_name):
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

    for pkg_name, item in sorted(matching_packages.items(), key=lambda x: -x[1]["counter"]):
        deps = item["deps"]
        if len(deps) == 1:
            print(item["counter"], pkg_name, [d.pkg_name for d in deps])


if __name__ == "__main__":
    main()
