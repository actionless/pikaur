#!/usr/bin/env python3

# import os
import sys
import asyncio
from urllib.parse import urlencode


def add(container, item):
    container += item


class TaskResult(object):
    pass


class CmdTaskResult(TaskResult):
    stderr = None
    stdout = None
    return_code = None

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


class AsyncExecutor(object):
    cmd = None
    stderr = None
    stdout = None
    enable_logging = None

    async def _read_stream(self, stream, cb):
        while True:
            line = await stream.readline()
            if line:
                if self.enable_logging:
                    print('>> {}'.format(line.decode('ascii')), end='')
                cb(line)
            else:
                break

    def save_err(self, line):
        self.stderr += line

    def save_out(self, line):
        self.stdout += line

    async def _on_process_done(self, process):
        # print(f"== DONE")
        result = CmdTaskResult()
        result.stderr = self.stderr.decode('ascii')
        result.stdout = self.stdout.decode('ascii')
        result.return_code = await process.wait()
        return result

    async def _stream_subprocess(self):
        process = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait([
            self._read_stream(process.stdout, self.save_out),
            self._read_stream(process.stderr, self.save_err)
        ])
        return await self._on_process_done(process)

    def __init__(self, cmd, enable_logging=False):
        self.cmd = cmd
        self.stderr = b''
        self.stdout = b''
        self.enable_logging = enable_logging

    def get_task(self, _loop):
        return self._stream_subprocess()


class MultipleCommandsExecutor(object):

    enable_logging = None

    def __init__(self, cmds, enable_logging=False):
        self.cmds = cmds
        self.results = {}
        self.futures = {}
        self.enable_logging = enable_logging

    def create_process_done_callback(self, cmd_id):

        def _process_done_callback(future):
            result = future.result()
            self.results[cmd_id] = result
            if len(self.results) == len(self.futures):
                # print('== LOOP STOP')
                self.loop.stop()

        return _process_done_callback

    def execute(self):
        cmds = self.cmds

        self.loop = asyncio.get_event_loop()
        for cmd_id, task_gen in cmds.items():
            future = self.loop.create_task(
                task_gen(self.loop)
            )
            future.add_done_callback(self.create_process_done_callback(cmd_id))
            self.futures[cmd_id] = future
        self.loop.run_forever()
        # print('== LOOP CLOSE')
        self.loop.close()
        return self.results


def color_line(line, color_number, bold=False):
    result = ''
    if bold:
        result += "\033[1m"
        color_number -= 8
    result += "\033[03{n}m{string}".format(
        n=color_number,
        string=line,
    )
    # reset font:
    result += "\033[0m"
    return result


def main():
    args = sys.argv[1:]
    print(f'args = {args}')
    operation = args[0]
    result = None

    if operation == '-Syu':
        result = MultipleCommandsExecutor({
            'proc1': AsyncExecutor([
                "bash", "-c",
                "echo stdout"
                " && sleep 1"
                " && echo stderr 1>&2"
                " && sleep 1"
                " && echo done"
            ]).get_task,
            'proc2': AsyncExecutor([
                "bash", "-c",
                "echo stdout2"
                " && sleep 1"
                " && echo stderr2 1>&2"
                " && sleep 1"
                " && echo done2"
            ]).get_task,
        }).execute()

    elif operation == '-Ss':
        from aur import search_packages
        result = MultipleCommandsExecutor({
            'pkgs': AsyncExecutor([
                "pacman",
                "--color=always",
            ] + args).get_task,
            'aur': lambda loop: search_packages(loop, args[1]),
        }, enable_logging=True).execute()
        print(result['pkgs'].stdout, end='')
        for aur_pkg in result['aur']['json']['results']:
            print("{}{} {} {}".format(
                color_line('aur/', 13, bold=True),
                color_line(aur_pkg['Name'], 15, bold=True),
                color_line(aur_pkg["Version"], 10, bold=True),
                '',  # [installed]
            ))
            print(f'    {aur_pkg["Description"]}')
            # print(aur_pkg)

    else:
        result = MultipleCommandsExecutor({
            'proc1': AsyncExecutor([
                # "sudo",
                "pacman",
                "--color=always",
            ] + args).get_task,
        }, enable_logging=True).execute()
        for key, value in result.items():
            print(f'{key}:')
            print(value)


if __name__ == '__main__':
    main()
