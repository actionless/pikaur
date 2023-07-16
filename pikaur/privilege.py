import os
from pathlib import Path

from .args import parse_args
from .config import (
    PikaurConfig,
    RunningAsRoot,
    UsingDynamicUsers,
    _UserTempRoot,
)
from .core import sudo as _sudo

sudo = _sudo


def need_dynamic_users() -> bool:
    args = parse_args()
    dynamic_users = PikaurConfig().build.DynamicUsers.get_str()
    if args.user_id:
        return False
    if args.dynamic_users:
        return True
    if dynamic_users == "never":
        return False
    if running_as_root() and dynamic_users == "root":
        return True
    return False


def using_dynamic_users() -> int:
    return UsingDynamicUsers()()


def running_as_root() -> int:
    return RunningAsRoot()()


def isolate_root_cmd(
        cmd: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
) -> list[str]:
    # @TODO: move to privilege module
    if not running_as_root():
        return cmd
    if isinstance(cwd, str):
        cwd = Path(cwd)
    args = parse_args()
    user_id = args.user_id
    base_root_isolator: list[str]
    if user_id:
        base_root_isolator = [
            PikaurConfig().misc.PrivilegeEscalationTool.get_str(),
            f"--user=#{user_id}",
            "--preserve-env",
            "--",
        ]
    else:
        base_root_isolator = [
            "/usr/sbin/systemd-run",
            "--service-type=oneshot",
            "--pipe", "--wait", "--pty",
            "-p", "DynamicUser=yes",
            "-p", "CacheDirectory=pikaur",
            "-E", f"HOME={_UserTempRoot()()}",
        ]
        if env is not None:
            for env_var_name, env_var_value in env.items():
                base_root_isolator += ["-E", f"{env_var_name}={env_var_value}"]
        if cwd is not None:
            base_root_isolator += ["-p", "WorkingDirectory=" + str(cwd.resolve())]
        for env_var_name in (
                "http_proxy", "https_proxy", "ftp_proxy",
        ):
            if os.environ.get(env_var_name) is not None:
                base_root_isolator += ["-E", f"{env_var_name}={os.environ[env_var_name]}"]
    return base_root_isolator + cmd
