#!/usr/bin/python3 -u
# pylint: disable=invalid-name
"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
import os  # ruff: ignore[unsorted-imports]
from typing import Final
PIKAUR_NAME_ENV_NAME: Final = "PIKAUR_NAME"
os.environ[PIKAUR_NAME_ENV_NAME] = os.environ.get(PIKAUR_NAME_ENV_NAME, "pikaur-static")
from pikaur.main import (  # pylint: disable=wrong-import-position  # ruff: ignore[module-import-not-at-top-of-file]
    main,
)

if __name__ == "__main__":
    main()
