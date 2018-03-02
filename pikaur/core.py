import asyncio
import configparser
import os
import shutil
import subprocess
from uuid import uuid1


NOT_FOUND_ATOM = object()


def interactive_spawn(cmd, **kwargs):
    process = subprocess.Popen(cmd, **kwargs)
    process.communicate()
    return process


def running_as_root():
    return os.geteuid() == 0


def isolate_root_cmd(cmd, cwd=None):
    if not running_as_root():
        return cmd
    base_root_isolator = ['systemd-run', '--pipe', '--wait',
                          '-p', 'DynamicUser=yes',
                          '-p', 'CacheDirectory=pikaur']
    if cwd is not None:
        base_root_isolator += ['-p', 'WorkingDirectory=' + cwd]
    return base_root_isolator + cmd


def get_event_loop():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


class MultipleTasksExecutor(object):
    loop = None
    executor_id = None
    futures = None
    export_results = None

    _all_cmds = {}
    _all_results = {}

    def __init__(self, cmds):
        self.executor_id = uuid1()
        self.cmds = cmds
        self.futures = {}

    @classmethod
    def _get_results(cls, executor_id):
        return cls._all_results.setdefault(executor_id, {})

    @property
    def results(self):
        return self._get_results(self.executor_id)

    @classmethod
    def _get_cmds(cls, executor_id):
        return cls._all_cmds[executor_id]

    @classmethod
    def _set_cmds(cls, executor_id, value):
        cls._all_cmds[executor_id] = value

    @property
    def cmds(self):
        return self._get_cmds(self.executor_id)

    @cmds.setter
    def cmds(self, value):
        self._set_cmds(self.executor_id, value)

    @property
    def all_tasks_done(self):
        return sum([
            len(self._all_results.get(exec_id, [])) == len(cmds)
            for exec_id, cmds in self._all_cmds.items()
        ]) == len(self._all_cmds)

    @classmethod
    def mark_executor_done(cls, executor_id):
        results = {}
        results.update(cls._get_results(executor_id))
        del cls._all_cmds[executor_id]
        del cls._all_results[executor_id]
        return results

    def create_process_done_callback(self, cmd_id):

        def _process_done_callback(future):
            result = future.result()
            self.results[cmd_id] = result
            if len(self.results) == len(self.cmds):
                self.export_results = self.mark_executor_done(self.executor_id)
            if self.all_tasks_done:
                self.loop.stop()

        return _process_done_callback

    def _execute_common(self):
        self.loop = get_event_loop()
        for cmd_id, task_class in self.cmds.items():
            future = self.loop.create_task(
                task_class.get_task(self.loop)
            )
            future.add_done_callback(self.create_process_done_callback(cmd_id))
            self.futures[cmd_id] = future

    def execute(self):
        self._execute_common()
        self.loop.run_forever()
        return self.export_results

    async def execute_async(self):
        self._execute_common()
        for future in self.futures.values():
            await future
        return self.export_results


class SingleTaskExecutor(MultipleTasksExecutor):

    def __init__(self, cmd):
        super().__init__({0: cmd})

    def execute(self):
        return super().execute()[0]

    async def execute_async(self):
        multi_result = await super().execute_async()
        return multi_result[0]


def create_worker_from_task(task):

    class StubWorker():
        async def get_task(self):
            return await task

    return StubWorker


def execute_task(task):
    return SingleTaskExecutor(create_worker_from_task(task)).execute()


class DataType():

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __setattr__(self, key, value):
        if getattr(self, key, NOT_FOUND_ATOM) is NOT_FOUND_ATOM:
            raise TypeError(
                f"'{self.__class__.__name__}' does "
                f"not have attribute '{key}'"
            )
        super().__setattr__(key, value)


class CmdTaskResult(DataType):
    stderrs = None
    stdouts = None
    return_code = None

    _stderr = None
    _stdout = None

    @property
    def stderr(self):
        if not self._stderr:
            self._stderr = '\n'.join(self.stderrs)
        return self._stderr

    @property
    def stdout(self):
        if not self._stdout:
            self._stdout = '\n'.join(self.stdouts)
        return self._stdout

    def __repr__(self):
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


class CmdTaskWorker(object):
    cmd = None
    kwargs = None
    enable_logging = None
    stderrs = None
    stdouts = None

    async def _read_stream(self, stream, callback):
        while True:
            line = await stream.readline()
            if line:
                if self.enable_logging:
                    print('>> {}'.format(line.decode('utf-8')), end='')
                callback(line)
            else:
                break

    def save_err(self, line):
        self.stderrs.append(line.rstrip(b'\n').decode('utf-8'))

    def save_out(self, line):
        self.stdouts.append(line.rstrip(b'\n').decode('utf-8'))

    async def _stream_subprocess(self):
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
        result = CmdTaskResult()
        result.return_code = await process.wait()
        result.stderrs = self.stderrs
        result.stdouts = self.stdouts
        return result

    def __init__(self, cmd, **kwargs):
        self.cmd = cmd
        self.stderrs = []
        self.stdouts = []
        self.kwargs = kwargs

    def get_task(self, _loop):
        return self._stream_subprocess()


class ConfigReader():

    _cached_config = None
    default_config_path = None
    list_fields = []
    ignored_fields = []

    @classmethod
    def _approve_line_for_parsing(cls, line):
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
    def get_config(cls, config_path=None):
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
    def get(cls, key, fallback=None, config_path=None):
        value = cls.get_config(config_path=config_path).get(key)
        if value:
            value = value.strip('"').strip("'")
        else:
            return fallback
        if key in cls.list_fields:
            value = value.split()
        return value


def remove_dir(dir_path):
    try:
        shutil.rmtree(dir_path)
    except PermissionError:
        interactive_spawn(['sudo', 'rm', '-rf', dir_path])


def get_chunks(iterable, chunk_size):
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
    loop = None
    pool_size = None
    tasks_queued = None

    last_cmd_idx = None

    def __init__(self, cmds, pool_size=None):
        super().__init__(cmds)
        self.cmds = list(cmds.items())
        from multiprocessing import cpu_count
        self.pool_size = pool_size or cpu_count()

    def get_next_cmd(self):
        if self.last_cmd_idx is not None:
            self.last_cmd_idx += 1
        else:
            self.last_cmd_idx = 0
        if self.last_cmd_idx > len(self.cmds):
            return None, None
        return self.cmds[self.last_cmd_idx]

    def add_more_tasks(self):
        while len(self.futures) < len(self.cmds):
            cmd_id, task_class = self.get_next_cmd()
            if cmd_id is None:
                return
            future = self.loop.create_task(
                task_class.get_task(self.loop)
            )
            future.add_done_callback(self.create_process_done_callback(cmd_id))
            self.futures[cmd_id] = future
            self.tasks_queued += 1
            if self.tasks_queued >= self.pool_size:
                break

    def create_process_done_callback(self, cmd_id):

        def _process_done_callback(future):
            result = future.result()
            self.results[cmd_id] = result
            if len(self.results) == len(self.cmds):
                self.export_results = self.mark_executor_done(self.executor_id)
            else:
                self.tasks_queued -= 1
                self.add_more_tasks()
            if self.all_tasks_done:
                self.loop.stop()

        return _process_done_callback

    def execute_common(self):
        self.loop = get_event_loop()
        self.tasks_queued = 0
        self.add_more_tasks()

    def execute(self):
        self.execute_common()
        self.loop.run_forever()
        return self.export_results

    async def execute_async(self):
        self.execute_common()
        for future in self.futures.values():
            await future
        return self.export_results
