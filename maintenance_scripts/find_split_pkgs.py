# pylint:disable=invalid-name

import os
import pickle
from typing import Dict, List

from pikaur.aur import get_all_aur_packages


PICKLE_FILE = 'aur_db.dump'


if os.path.exists(PICKLE_FILE):
    print(f"Opening db dump '{PICKLE_FILE}'...")
    with open(PICKLE_FILE, 'rb') as fobj:
        aur_pkgs = pickle.load(fobj)
else:
    print("Fetching...")
    aur_pkgs = get_all_aur_packages()
    print(f"Saving db dump to '{PICKLE_FILE}'...")
    with open(PICKLE_FILE, 'wb') as fobj:
        pickle.dump(aur_pkgs, fobj)

print("Filtering...\n")
pkgbases: Dict[str, List[str]] = {}
for pkg in aur_pkgs:
    pkgbases.setdefault(pkg.packagebase, []).append(pkg.name)

# Print all split-packages:
for pkgbase, pkgnames in pkgbases.items():
    if len(pkgnames) > 1:
        print(f'{pkgbase}: {pkgnames}')
