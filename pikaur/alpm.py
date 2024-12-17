"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

from typing import TYPE_CHECKING

import pyalpm
from pycman.config import PacmanConfig as PycmanConfig

from .args import parse_args
from .i18n import translate

if TYPE_CHECKING:
    from typing import Final


OFFICIAL_REPOS: "Final" = (
    "core",
    "extra",
    "multilib",
    "core-testing",
    "extra-testing",
    "multilib-testing",
    "core-staging",
    "extra-staging",
    "multilib-staging",
    "core-debug",
    "extra-debug",
    "multilib-debug",
)


class PacmanConfig(PycmanConfig):

    def __init__(self) -> None:
        args = parse_args()
        super().__init__(conf=args.config or "/etc/pacman.conf")
        if args.root:
            self.options["RootDir"] = args.root
        if args.dbpath:
            self.options["DBPath"] = args.dbpath


class PyAlpmWrapper:
    _alpm_handle: pyalpm.Handle | None = None

    @classmethod
    def get_alpm_handle(cls) -> pyalpm.Handle:
        if not cls._alpm_handle:
            cls._alpm_handle = PacmanConfig().initialize_alpm()
        if not cls._alpm_handle:
            cant_init_alpm = translate("Cannot initialize ALPM")
            raise RuntimeError(cant_init_alpm)
        return cls._alpm_handle
