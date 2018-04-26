import os
from typing import Optional, Any

from .core import ConfigReader
from .config import CONFIG_ROOT


class MakepkgConfig():

    _user_makepkg_path = "unset"

    @classmethod
    def get_user_makepkg_path(cls) -> Optional[str]:
        if cls._user_makepkg_path == 'unset':
            possible_paths = [
                os.path.expanduser('~/.makepkg.conf'),
                os.path.join(CONFIG_ROOT, "pacman/makepkg.conf"),
            ]
            config_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
            cls._user_makepkg_path = config_path
        return cls._user_makepkg_path

    @classmethod
    def get(cls, key: str, fallback: Any = None, config_path: str = None) -> Any:
        value = ConfigReader.get(key, fallback, config_path="/etc/makepkg.conf")
        if cls.get_user_makepkg_path():
            value = ConfigReader.get(key, value, config_path=cls.get_user_makepkg_path())
        if config_path:
            value = ConfigReader.get(key, value, config_path=config_path)
        return value
