import asyncio
import configparser
import os
import shutil
import subprocess
import enum
import uuid
from abc import ABCMeta
from typing import Dict, Any, List, Callable, Awaitable, Iterable, Tuple


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


def get_event_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


class TaskWorkerInterface(ABCMeta):

    def get_task(cls, _loop: asyncio.AbstractEventLoop) -> asyncio.Task:
        pass


class TaskWorker(metaclass=TaskWorkerInterface):
    pass


class MultipleTasksExecutor(object):
    loop: asyncio.AbstractEventLoop = None
    executor_id: uuid.UUID = None
    _all_cmds: Dict[uuid.UUID, Dict[str, TaskWorker]] = {}
    futures: Dict[str, asyncio.Task] = None
    _all_results: Dict[uuid.UUID, Dict[str, Any]] = {}
    export_results: Dict[str, Any] = None

    def __init__(self, cmds: Dict[str, TaskWorker]) -> None:
        self.executor_id = uuid.uuid1()
        self.cmds = cmds
        self.futures = {}

    @classmethod
    def _get_results(cls, executor_id) -> Dict[str, Any]:
        return cls._all_results.setdefault(executor_id, {})

    @property
    def results(self) -> Dict[str, Any]:
        return self._get_results(self.executor_id)

    @classmethod
    def _get_cmds(cls, executor_id: uuid.UUID) -> Dict[str, TaskWorker]:
        return cls._all_cmds[executor_id]

    @classmethod
    def _set_cmds(cls, executor_id: uuid.UUID, value: Any) -> None:
        cls._all_cmds[executor_id] = value

    @property
    def cmds(self) -> Dict[str, TaskWorker]:
        return self._get_cmds(self.executor_id)

    @cmds.setter
    def cmds(self, value: Any) -> None:
        self._set_cmds(self.executor_id, value)

    @property
    def all_tasks_done(self) -> bool:
        return sum([
            len(self._all_results.get(exec_id, [])) == len(cmds)
            for exec_id, cmds in self._all_cmds.items()
        ]) == len(self._all_cmds)

    @classmethod
    def mark_executor_done(cls, executor_id: uuid.UUID) -> Dict[str, Any]:
        results = {}
        results.update(cls._get_results(executor_id))
        del cls._all_cmds[executor_id]
        del cls._all_results[executor_id]
        return results

    def create_process_done_callback(self, cmd_id: str) -> Callable[[asyncio.Task], None]:

        def _process_done_callback(future: asyncio.Task) -> None:
            result = future.result()
            self.results[cmd_id] = result
            if len(self.results) == len(self.cmds):
                self.export_results = self.mark_executor_done(self.executor_id)
            if self.all_tasks_done:
                self.loop.stop()

        return _process_done_callback

    def _execute_common(self) -> None:
        self.loop = get_event_loop()
        for cmd_id, task_class in self.cmds.items():
            future = self.loop.create_task(
                task_class.get_task(self.loop)  # type: ignore
            )
            future.add_done_callback(self.create_process_done_callback(cmd_id))
            self.futures[cmd_id] = future

    def execute(self) -> Dict[str, Any]:
        self._execute_common()
        self.loop.run_forever()
        return self.export_results

    async def execute_async(self) -> Dict[str, Any]:
        self._execute_common()
        for future in self.futures.values():
            await future
        return self.export_results


class SingleTaskExecutor():

    _multi_executor: MultipleTasksExecutor = None
    _id = "_single"

    def __init__(self, cmd: TaskWorker) -> None:
        self._multi_executor = MultipleTasksExecutor({self._id: cmd})

    def execute(self) -> Any:
        return self._multi_executor.execute()[self._id]

    async def execute_async(self) -> Any:
        multi_result = await self._multi_executor.execute_async()
        return multi_result[self._id]


def create_worker_from_task(task: asyncio.Task) -> TaskWorker:

    class StubWorker(TaskWorker):
        async def get_task(self) -> asyncio.Task:
            return await task

    return StubWorker()


def execute_task(task: asyncio.Task) -> Any:
    return SingleTaskExecutor(create_worker_from_task(task)).execute()


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


class CmdTaskResult(DataType):
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

    def __init__(self, cmd, **kwargs):
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


class MultipleTasksExecutorPool(MultipleTasksExecutor):
    loop: asyncio.AbstractEventLoop = None
    pool_size: int = None
    tasks_queued: int = None
    last_cmd_idx: int = None
    indexed_cmds: List[Tuple[str, TaskWorker]] = None

    progress_bar = None

    def __init__(
            self,
            cmds: Dict[str, TaskWorker],
            pool_size: int = None,
            enable_progressbar=False
    ) -> None:
        super().__init__(cmds)
        self.indexed_cmds = list(cmds.items())
        from multiprocessing import cpu_count
        self.pool_size = pool_size or cpu_count()
        if enable_progressbar:
            import sys
            from .pprint import ProgressBar
            sys.stderr.write('\n')
            self.progress_bar = ProgressBar(
                message=enable_progressbar,
                length=len(cmds)
            )

    def get_next_cmd(self) -> Tuple[str, TaskWorker]:
        if self.last_cmd_idx is not None:
            self.last_cmd_idx += 1
        else:
            self.last_cmd_idx = 0
        if self.last_cmd_idx > len(self.indexed_cmds):
            return None, None
        return self.indexed_cmds[self.last_cmd_idx]

    def add_more_tasks(self) -> None:
        while len(self.futures) < len(self.indexed_cmds):
            cmd_id, task_class = self.get_next_cmd()
            if cmd_id is None:
                return
            future = self.loop.create_task(
                task_class.get_task(self.loop)  # type: ignore
            )
            future.add_done_callback(self.create_process_done_callback(cmd_id))
            self.futures[cmd_id] = future
            self.tasks_queued += 1
            if self.tasks_queued >= self.pool_size:
                break

    def create_process_done_callback(self, cmd_id: str) -> Callable[[asyncio.Task], None]:

        def _process_done_callback(future: asyncio.Task) -> None:
            if self.progress_bar:
                self.progress_bar.update()
            result = future.result()
            self.results[cmd_id] = result
            if len(self.results) == len(self.indexed_cmds):
                self.export_results = self.mark_executor_done(self.executor_id)
            else:
                self.tasks_queued -= 1
                self.add_more_tasks()
            if self.all_tasks_done:
                self.loop.stop()

        return _process_done_callback

    def _execute_common(self) -> None:
        self.loop = get_event_loop()
        self.tasks_queued = 0
        self.add_more_tasks()
