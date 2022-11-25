from argparse import Namespace
from collections import OrderedDict
from typing import Optional, Union
from typing_extensions import TypedDict

from pyalpm import Handle


class PacmanOptions(TypedDict):
    IgnorePkg: list[str]


class PacmanConfig(object):
    options: PacmanOptions
    repos: OrderedDict[str, list[str]]
    # def __init__(self, conf: Optional[str], options: Optional[Namespace]) -> None: ...  # @TODO: figure it out
    def __init__(self, conf: Optional[str]) -> None: ...
    def load_from_file(self, filename: str) -> None: ...
    def load_from_options(self, options: Namespace) -> None: ...
    def apply(self, h: Handle) -> None: ...
    def initialize_alpm(self) -> Handle: ...
    def __str__(self) -> str: ...

# vim: ft=python
