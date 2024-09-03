#!/usr/bin/python3 -u
"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import os
PIKAUR_NAME_ENV_NAME = "PIKAUR_NAME"
os.environ[PIKAUR_NAME_ENV_NAME] = os.environ.get(PIKAUR_NAME_ENV_NAME, "pikaur-static")
from pikaur.main import main  # pylint: disable=wrong-import-position  # noqa: E402

if __name__ == "__main__":
    main()
