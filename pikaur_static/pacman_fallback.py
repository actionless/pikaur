# pylint: disable=invalid-name,too-many-branches,too-many-statements  # noqa: INP001
import asyncio
import os
from collections.abc import Callable, Coroutine, Iterable, Sequence
from typing import TYPE_CHECKING, Any, Final, TypedDict, cast

if TYPE_CHECKING:
    from pypyalpm import Handle
    from pypyalpm import PackageDBCommon as PackageDBCommonType
    from pypyalpm import PacmanPackageInfo as PacmanPackageInfoType


class PacmanExecutablesPaths:

    _pacman: str | None = None
    _pacman_conf: str | None = None

    @classmethod
    def init(cls) -> None:
        # pylint: disable=import-outside-toplevel
        if not cls._pacman:
            try:
                from pikaur.args import (  # pylint: disable=no-name-in-module,useless-suppression  # noqa: PLC0415,E501,RUF100
                    parse_args,
                )
                cls._pacman = parse_args().pacman_path
                cls._pacman_conf = parse_args().pacman_conf_path
            except Exception as exc:
                print(exc)
                cls._pacman = "pacman"
                cls._pacman_conf = "pacman-conf"
            # print(cls._pacman, cls._pacman_conf)

    @classmethod
    def pacman(cls) -> str:
        cls.init()
        return cast(str, cls._pacman)

    @classmethod
    def pacman_conf(cls) -> str:
        cls.init()
        return cast(str, cls._pacman_conf)


class CmdTaskResult:
    stderrs: list[str] | None = None
    stdouts: list[str] | None = None
    return_code: int | None = None

    _stderr = None
    _stdout = None

    @property
    def stderr(self) -> str:
        if not self._stderr:
            self._stderr = "\n".join(self.stderrs or [])
        return self._stderr

    @property
    def stdout(self) -> str:
        if not self._stdout:
            self._stdout = "\n".join(self.stdouts or [])
        return self._stdout

    def __repr__(self) -> str:
        result = f"[rc: {self.return_code}]\n"
        if self.stderr:
            result += "\n".join([
                "=======",
                "errors:",
                "=======",
                f"{self.stderr}",
            ])
        result += "\n".join([
            "-------",
            "output:",
            "-------",
            f"{self.stdout}",
        ])
        return result


class CmdTaskWorker:
    cmd: list[str]
    kwargs: dict[str, Any]
    enable_logging = None
    stderrs: list[str]
    stdouts: list[str]

    async def _read_stream(
            self, stream: asyncio.StreamReader, callback: Callable[[bytes], None],
    ) -> None:
        while True:
            line = await stream.readline()
            if line:
                if self.enable_logging:
                    pass
                callback(line)
            else:
                break

    def save_err(self, line: bytes) -> None:
        self.stderrs.append(line.rstrip(b"\n").decode("utf-8"))

    def save_out(self, line: bytes) -> None:
        self.stdouts.append(line.rstrip(b"\n").decode("utf-8"))

    async def _stream_subprocess(self) -> CmdTaskResult:
        env = os.environ.copy()
        env["LANGUAGE"] = "en"
        process = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            **self.kwargs,
        )
        if (not process.stdout) or (not process.stderr):
            msg = "no stdout or stderr"
            raise RuntimeError(msg)
        await asyncio.wait([
            asyncio.create_task(self._read_stream(process.stdout, self.save_out)),
            asyncio.create_task(self._read_stream(process.stderr, self.save_err)),
        ])
        result = CmdTaskResult()
        result.return_code = await process.wait()
        result.stderrs = self.stderrs
        result.stdouts = self.stdouts
        return result

    def __init__(self, cmd: list[str], **kwargs: dict[str, Any]) -> None:
        self.cmd = cmd
        self.stderrs = []
        self.stdouts = []
        self.kwargs = kwargs

    def get_task(self, _loop: asyncio.AbstractEventLoop) -> Coroutine[Any, Any, CmdTaskResult]:
        return self._stream_subprocess()


class MultipleTasksExecutor:
    loop: asyncio.AbstractEventLoop | None = None
    cmds: dict[str, CmdTaskWorker]
    results: dict[str, CmdTaskResult]
    futures: dict[str, asyncio.Task[CmdTaskResult]]

    def __init__(self, cmds: dict[str, CmdTaskWorker]) -> None:
        self.cmds = cmds
        self.results = {}
        self.futures = {}

    def create_process_done_callback(
            self, cmd_id: str,
    ) -> Callable[[asyncio.Task[CmdTaskResult]], None]:

        def _process_done_callback(future: asyncio.Task[CmdTaskResult]) -> None:
            result = future.result()
            self.results[cmd_id] = result
            if len(self.results) == len(self.futures):
                if not self.loop:
                    msg = "eventloop lost"
                    raise RuntimeError(msg)
                self.loop.stop()

        return _process_done_callback

    def execute(self) -> dict[str, CmdTaskResult]:
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
        for cmd_id, task_class in self.cmds.items():
            future = self.loop.create_task(
                task_class.get_task(self.loop),
            )
            future.add_done_callback(self.create_process_done_callback(cmd_id))
            self.futures[cmd_id] = future
        if self.loop.is_running():
            pass
        self.loop.run_forever()
        return self.results


class SingleTaskExecutor:

    def __init__(self, cmd: CmdTaskWorker) -> None:
        self.executor = MultipleTasksExecutor({"0": cmd})

    def execute(self) -> CmdTaskResult:
        return self.executor.execute()["0"]


class PacmanTaskWorker(CmdTaskWorker):

    def __init__(self, args: list[str]) -> None:
        pacman_executable = PacmanExecutablesPaths.pacman()
        super().__init__(
            [pacman_executable, *args],
        )


CLI_TO_DB_TRANSLATION: Final[dict[str, str]] = {
    "description": "desc",
    "architecture": "arch",
    "validated_by": "validation",
    "depends_on": "depends",
    "optional_deps": "optdepends",
    "download_size": "size",
    "installed_size": "isize",
    "conflicts_with": "conflicts",
    "build_date": "builddate",
    "install_date": "installdate",
    "install_reason": "reason",
    "install_script": "has_scriptlet",
}


class DBPlaceholder:

    def __init__(self, name: str) -> None:
        self.name = name


def get_pacman_cli_package_db(  # noqa: C901
        PackageDBCommon: "type[PackageDBCommonType]",  # noqa: N803
        PacmanPackageInfo: "type[PacmanPackageInfoType]",  # noqa: N803
        PACMAN_DICT_FIELDS: Sequence[str],  # noqa: N803
        PACMAN_LIST_FIELDS: Sequence[str],  # noqa: N803
        PACMAN_INT_FIELDS: Sequence[str],  # noqa: N803
) -> "type[PackageDBCommonType]":

    class CliPackageInfo(PacmanPackageInfo):  # type: ignore[valid-type,misc]
        db: DBPlaceholder
        repository: str

        required_by: list[str] | None = None
        optional_for: list[str] | None = None

        reason: bool

        def compute_requiredby(self) -> list[str]:
            return self.required_by or []

        def compute_optionalfor(self) -> list[str]:
            return self.optional_for or []

        @classmethod
        def parse_pacman_cli_info(
                cls, lines: list[str], db_type: str,
        ) -> Iterable["CliPackageInfo"]:
            pkg = cls()
            field: str | None
            value: str | list[str] | dict[str, str | None] | None
            field = value = None
            for line in lines:
                if line == "":  # noqa: PLC1901
                    if db_type == "local":
                        pkg.db = DBPlaceholder(name="local")
                    else:
                        pkg.db = DBPlaceholder(name=pkg.repository)
                        del pkg.repository
                    pkg.reason = "dependency" in (cast(str, pkg.reason) or "").lower()
                    yield pkg
                    pkg = cls()
                    continue
                if not line.startswith(" "):
                    try:
                        _field, _value, *_args = line.split(": ")
                    except ValueError:
                        print(line)
                        print(field, value)
                        raise
                    _value = _value.lstrip(" \t")
                    field = _field.rstrip().replace(" ", "_").lower()
                    field = CLI_TO_DB_TRANSLATION.get(field, field)
                    if _value == "None":
                        value = None
                    else:
                        if field in PACMAN_DICT_FIELDS:
                            value = {_value: None}
                        elif field in PACMAN_LIST_FIELDS:
                            value = _value.split()
                        else:
                            value = _value
                        if _args:
                            if field in PACMAN_DICT_FIELDS:
                                value = {_value: _args[0].lstrip()}
                            else:
                                value = ": ".join([_value, *_args])
                                if field in PACMAN_LIST_FIELDS:
                                    value = value.split()
                elif field in PACMAN_DICT_FIELDS:
                    _value, *_args = line.split(": ")
                    _value = _value.lstrip(" \t")
                    # pylint: disable=unsupported-assignment-operation
                    value[_value] = _args[0] if _args else None  # type: ignore[index,call-overload]
                elif field in PACMAN_LIST_FIELDS:
                    value += line.split()  # type: ignore[operator]
                else:
                    value += line  # type: ignore[operator]

                if (
                        field
                        and (
                            value
                            or not (
                                (field in PACMAN_DICT_FIELDS)
                                or (field in PACMAN_INT_FIELDS)
                                or (field in PACMAN_LIST_FIELDS)
                            )
                        )
                ):
                    try:
                        setattr(pkg, field, value)
                    except TypeError:
                        print(line)
                        raise

    class MergedDBCache(TypedDict):
        local: list[CliPackageInfo]
        repo: list[CliPackageInfo]

    class PackageDbCli(PackageDBCommon):  # type: ignore[valid-type,misc]

        # -Qu --repo: ~ 2.8..3.3 s
        #  #  ~4.7 seconds

        repo = "repo"
        local = "local"

        @classmethod
        def _get_dbs(
                cls,
                handle: "Handle | None" = None,  # pylint: disable=unused-argument  # noqa: ARG003,E501,RUF100
        ) -> MergedDBCache:
            if not cls._repo_cache:
                print(" >>> Retrieving local pacman database...")
                results = MultipleTasksExecutor({
                    cls.repo: PacmanTaskWorker(["-Si"]),
                    cls.local: PacmanTaskWorker(["-Qi"]),
                }).execute()
                repo_stdouts = results[cls.repo].stdouts
                if not repo_stdouts:
                    msg = "no repo stdout"
                    raise RuntimeError(msg)
                local_stdouts = results[cls.local].stdouts
                if not local_stdouts:
                    msg = "no local stdout"
                    raise RuntimeError(msg)
                cls._repo_cache = list(CliPackageInfo.parse_pacman_cli_info(
                    repo_stdouts, db_type="repo",
                ))
                cls._local_cache = list(CliPackageInfo.parse_pacman_cli_info(
                    local_stdouts, db_type="local",
                ))
            return {"repo": cls._repo_cache, "local": cls._local_cache}

        @classmethod
        def get_repo_list(
                cls,
                handle: "Handle | None" = None,  # pylint: disable=unused-argument  # noqa: ARG003,E501,RUF100
        ) -> list[CliPackageInfo]:
            # print(" >>> GET_REPO_LIST")
            return cls._get_dbs()["repo"]

        @classmethod
        def get_local_list(
                cls,
                handle: "Handle | None" = None,  # pylint: disable=unused-argument  # noqa: ARG003,E501,RUF100
        ) -> list[CliPackageInfo]:
            # print(" >>> GET_LOCAL_LIST")
            return cls._get_dbs()["local"]

        _repo_db_names: list[str] | None = None

        @classmethod
        def get_db_names(
                cls,
                handle: "Handle | None" = None,  # pylint: disable=unused-argument  # noqa: ARG003,E501,RUF100
        ) -> list[str]:
            if not cls._repo_db_names:
                result = SingleTaskExecutor(
                    CmdTaskWorker([PacmanExecutablesPaths.pacman_conf(), "--repo-list"]),
                ).execute()
                if not result.stdouts:
                    msg = "no dbs found"
                    raise RuntimeError(msg)
                cls._repo_db_names = result.stdouts
            return cls._repo_db_names

        @classmethod
        def get_local_pkg_uncached(
                cls,
                name: str,
                handle: "Handle | None" = None,  # pylint: disable=unused-argument  # noqa: ARG003,E501,RUF100
        ) -> "PacmanPackageInfoType | None":
            result = SingleTaskExecutor(
                PacmanTaskWorker(["-Qi", name]),
            ).execute()
            if not result.stdouts:
                return None
            pkgs = list(CliPackageInfo.parse_pacman_cli_info(
                result.stdouts, db_type="local",
            ))
            if not pkgs:
                print(result.stdouts)
                raise RuntimeError(name)
            return pkgs[0]

    return PackageDbCli
