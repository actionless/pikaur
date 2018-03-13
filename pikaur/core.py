import asyncio
import configparser
import os
import shutil
import subprocess
import enum
from typing import (
    TYPE_CHECKING,
    Dict, Any, List, Callable, Awaitable, Iterable
)

from .async import TaskWorker

if TYPE_CHECKING:
    # pylint: disable=unused-import
    from .pprint import ProgressBar  # noqa


NOT_FOUND_ATOM = object()


class PackageSource(enum.Enum):
    REPO = enum.auto()
    AUR = enum.auto()
    LOCAL = enum.auto()


def interactive_spawn(cmd: List[str], **kwargs) -> subprocess.Popen:
    process = subprocess.Popen(cmd, **kwargs)
    process.communicate()
    return process


def running_as_root() -> bool:
    return os.geteuid() == 0


def isolate_root_cmd(cmd: List[str], cwd=None) -> List[str]:
    if not running_as_root():
        return cmd
    base_root_isolator = ['systemd-run', '--pipe', '--wait',
                          '-p', 'DynamicUser=yes',
                          '-p', 'CacheDirectory=pikaur']
    if cwd is not None:
        base_root_isolator += ['-p', 'WorkingDirectory=' + cwd]
    return base_root_isolator + cmd


class DataType():

    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __setattr__(self, key: str, value: Any) -> None:
        if getattr(self, key, NOT_FOUND_ATOM) is NOT_FOUND_ATOM:
            raise TypeError(
                f"'{self.__class__.__name__}' does "
                f"not have attribute '{key}'"
            )
        super().__setattr__(key, value)


class TaskResult(DataType):
    pass


class CmdTaskResult(TaskResult):
    stderrs: List[str] = None
    stdouts: List[str] = None
    return_code: int = None

    _stderr: str = None
    _stdout: str = None

    @property
    def stderr(self) -> str:
        if not self._stderr:
            self._stderr = '\n'.join(self.stderrs)
        return self._stderr

    @property
    def stdout(self) -> str:
        if not self._stdout:
            self._stdout = '\n'.join(self.stdouts)
        return self._stdout

    def __repr__(self) -> str:
        result = f"[rc: {self.return_code}]\n"
        if self.stderr:
            result += '\n'.join([
                "=======",
                "errors:",
                "=======",
                "{}".format(self.stderr)
            ])
        result += '\n'.join([
            "-------",
            "output:",
            "-------",
            "{}".format(self.stdout)
        ])
        return result


class CmdTaskWorker(TaskWorker):
    cmd: List[str] = None
    kwargs: Dict[str, Any] = None
    enable_logging: bool = None
    stderrs: List[str] = None
    stdouts: List[str] = None

    async def _read_stream(
            self, stream: asyncio.StreamReader, callback: Callable[[bytes], None]
    ) -> None:
        while True:
            line = await stream.readline()
            if line:
                if self.enable_logging:
                    print('>> {}'.format(line.decode('utf-8')), end='')
                callback(line)
            else:
                break

    def save_err(self, line: bytes) -> None:
        self.stderrs.append(line.rstrip(b'\n').decode('utf-8'))

    def save_out(self, line: bytes) -> None:
        self.stdouts.append(line.rstrip(b'\n').decode('utf-8'))

    async def _stream_subprocess(self) -> CmdTaskResult:
        process = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **self.kwargs
        )
        await asyncio.wait([
            self._read_stream(process.stdout, self.save_out),
            self._read_stream(process.stderr, self.save_err)
        ])
        result = CmdTaskResult(
            return_code=await process.wait(),
            stderrs=self.stderrs,
            stdouts=self.stdouts
        )
        return result

    def __init__(self, cmd: List[str], **kwargs) -> None:
        self.cmd = cmd
        self.stderrs = []
        self.stdouts = []
        self.kwargs = kwargs

    def get_task(self, _loop: asyncio.AbstractEventLoop) -> Awaitable[CmdTaskResult]:
        return self._stream_subprocess()


class ConfigReader():

    _cached_config: Dict[str, configparser.SectionProxy] = None
    default_config_path: str = None
    list_fields: List[str] = []
    ignored_fields: List[str] = []

    @classmethod
    def _approve_line_for_parsing(cls, line: str) -> bool:
        if line.startswith(' '):
            return False
        if '=' not in line:
            return False
        if not cls.ignored_fields:
            return True
        field_area = line.split('=')[0]
        for field in cls.ignored_fields:
            if field in field_area:
                return False
        return True

    @classmethod
    def get_config(cls, config_path: str = None) -> configparser.SectionProxy:
        config_path = config_path or cls.default_config_path
        if not cls._cached_config:
            cls._cached_config = {}
        if not cls._cached_config.get(config_path):
            config = configparser.ConfigParser(
                allow_no_value=True,
                strict=False,
                inline_comment_prefixes=('#', ';')
            )
            with open(config_path) as config_file:
                config_string = '\n'.join(['[all]'] + [
                    line for line in config_file.readlines()
                    if cls._approve_line_for_parsing(line)
                ])
            config.read_string(config_string)
            cls._cached_config[config_path] = config['all']
        return cls._cached_config[config_path]

    @classmethod
    def get(cls, key: str, fallback: Any = None, config_path: str = None) -> Any:
        value = cls.get_config(config_path=config_path).get(key)
        if value:
            value = value.strip('"').strip("'")
        else:
            return fallback
        if key in cls.list_fields:
            return value.split()
        return value


def remove_dir(dir_path: str) -> None:
    try:
        shutil.rmtree(dir_path)
    except PermissionError:
        interactive_spawn(['sudo', 'rm', '-rf', dir_path])


def get_chunks(iterable: Iterable[Any], chunk_size: int) -> Iterable[List[Any]]:
    result = []
    index = 0
    for item in iterable:
        result.append(item)
        index += 1
        if index == chunk_size:
            yield result
            result = []
            index = 0
    if result:
        yield result
