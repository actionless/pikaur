import pickle  # nosec B403
from pathlib import Path
from typing import Final

from pikaur.aur import get_all_aur_packages
from pikaur.pikatypes import AURPackageInfo

PICKLE_FILE: Final = Path("aur_db.dump")


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
