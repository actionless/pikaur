import asyncio
import subprocess
from distutils.version import LooseVersion

from .pprint import color_line


NOT_FOUND_ATOM = object()


def interactive_spawn(cmd, **kwargs):
    process = subprocess.Popen(cmd, **kwargs)
    process.communicate()
    return process


class MultipleTasksExecutor(object):
    loop = None

    def __init__(self, cmds):
        self.cmds = cmds
        self.results = {}
        self.futures = {}

    def create_process_done_callback(self, cmd_id):

        def _process_done_callback(future):
            result = future.result()
            self.results[cmd_id] = result
            if len(self.results) == len(self.futures):
                self.loop.stop()

        return _process_done_callback

    def execute(self):
        self.loop = asyncio.get_event_loop()
        for cmd_id, task_class in self.cmds.items():
            future = self.loop.create_task(
                task_class.get_task(self.loop)
            )
            future.add_done_callback(self.create_process_done_callback(cmd_id))
            self.futures[cmd_id] = future
        if self.loop.is_running():
            print("DEBUG989817")
        self.loop.run_forever()
        return self.results


class SingleTaskExecutor(MultipleTasksExecutor):

    def __init__(self, cmd):
        super().__init__({0: cmd})

    def execute(self):
        return super().execute()[0]


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


def compare_versions(current_version, new_version):
    if current_version != new_version:
        for separator in ('+',):
            current_version = current_version.replace(separator, '.')
            new_version = new_version.replace(separator, '.')
        current_base_version = new_base_version = None
        for separator in (':',):
            if separator in current_version:
                current_base_version, _current_version = \
                    current_version.split(separator)[:2]
            if separator in new_version:
                new_base_version, _new_version = \
                    new_version.split(separator)[:2]
            if (
                    current_base_version and new_base_version
            ) and (
                current_base_version != new_base_version
            ):
                current_version = current_base_version
                new_version = new_base_version
                break

        versions = [current_version, new_version]
        try:
            versions.sort(key=LooseVersion)
        except TypeError:
            # print(versions)
            return False
        return versions[1] == new_version
    return False


def get_package_name_from_depend_line(depend_line):  # pylint: disable=invalid-name
    # @TODO: remove this one and use next function instead
    return depend_line.split('=')[0].split('<')[0].split('>')[0]


# pylint: disable=invalid-name
def get_package_name_and_version_matcher_from_depend_line(depend_line):
    version = None

    def get_version():
        return version

    cond = None
    version_matcher = lambda v: True  # noqa
    for test_cond, matcher in {
        '>=': lambda v: v >= get_version(),
        '<=': lambda v: v <= get_version(),
        '=': lambda v: v == get_version(),
        '>': lambda v: v > get_version(),
        '<': lambda v: v < get_version(),
    }.items():
        if test_cond in depend_line:
            cond = test_cond
            version_matcher = matcher
            break

    if cond:
        pkg_name, version = depend_line.split(cond)[:2]
    else:
        pkg_name = depend_line
    return pkg_name, version_matcher


def ask_to_continue(text='Do you want to proceed?', default_yes=True):
    answer = input(text + (' [Y/n] ' if default_yes else ' [y/N] '))
    if default_yes:
        if answer and answer.lower()[0] != 'y':
            return False
    else:
        if not answer or answer.lower()[0] != 'y':
            return False
    return True


def ask_to_retry_decorator(fun):

    def decorated(*args, **kwargs):
        while True:
            result = fun(*args, **kwargs)
            if result:
                return result
            if not ask_to_continue('Do you want to retry?'):
                return None

    return decorated


@ask_to_retry_decorator
def retry_interactive_command(cmd_args):
    good = interactive_spawn(cmd_args).returncode == 0
    if not good:
        print(color_line('Command "{}" failed to execute.'.format(
            ' '.join(cmd_args)
        ), 9))
    return good
