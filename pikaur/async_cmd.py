import asyncio
from typing import (
    Dict, Any, List, Callable, Awaitable,
)

from .async import TaskWorker, TaskResult
from .core import DataType


class CmdTaskResult(TaskResult, DataType):
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
