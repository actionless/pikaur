import asyncio
import uuid
from abc import ABCMeta, abstractmethod
from typing import (
    TYPE_CHECKING,
    Dict, Any, List, Callable, Tuple, Awaitable,
)

if TYPE_CHECKING:
    from .pprint import ProgressBar  # noqa  pylint: disable=unused-import


def get_event_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


class TaskWorker(metaclass=ABCMeta):

    @abstractmethod
    def get_task(self, _loop: asyncio.AbstractEventLoop) -> Awaitable[Any]:
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


class MultipleTasksExecutorPool(MultipleTasksExecutor):
    loop: asyncio.AbstractEventLoop = None
    pool_size: int = None
    tasks_queued: int = None
    last_cmd_idx: int = None
    indexed_cmds: List[Tuple[str, TaskWorker]] = None

    progress_bar: 'ProgressBar' = None

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
            from .pprint import ProgressBar  # noqa pylint: disable=redefined-outer-name
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
        def get_task(self, _loop=None) -> Awaitable[Any]:
            return task

    return StubWorker()


def execute_task(task: asyncio.Task) -> Any:
    return SingleTaskExecutor(create_worker_from_task(task)).execute()
