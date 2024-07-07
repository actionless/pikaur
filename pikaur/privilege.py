import os
from pathlib import Path

from .args import parse_args
from .config import (
    ConfigPath,
    PikaurConfig,
    RunningAsRoot,
    _UserTempRoot,
)


def get_envs_to_preserve() -> list[str]:
    return [
        env_var_name
        for env_var_name in parse_args().preserve_env.split(",")
        if os.environ.get(env_var_name) is not None
    ]


def need_dynamic_users() -> bool:
    args = parse_args()
    dynamic_users = PikaurConfig().build.DynamicUsers.get_str()
    if args.user_id:
        return False
    if args.dynamic_users:
        return True
    if dynamic_users == "never":
        return False
    return bool(RunningAsRoot() and dynamic_users == "root")


def sudo(cmd: list[str], preserve_env: list[str] | None = None) -> list[str]:
    if RunningAsRoot():
        return cmd
    if PikaurConfig().misc.PrivilegeEscalationTool.get_str() == "doas":
        return [PikaurConfig().misc.PrivilegeEscalationTool.get_str(), *cmd]
    result = [PikaurConfig().misc.PrivilegeEscalationTool.get_str()]
    if preserve_env:
        result.append("--preserve-env=" + ",".join(preserve_env))
    result += ["--", *cmd]
    return result


def isolate_root_cmd(
        cmd: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
) -> list[str]:
    if not RunningAsRoot():
        return cmd
    if isinstance(cwd, str):
        cwd = Path(cwd)
    env = env or {}
    args = parse_args()
    user_id = args.user_id
    base_root_isolator: list[str]
    preserve_envs = get_envs_to_preserve()
    if user_id:
        preserve_envs += list(env.keys())
        if PikaurConfig().misc.PrivilegeEscalationTool.get_str() == "doas":
            base_root_isolator = [
                PikaurConfig().misc.PrivilegeEscalationTool.get_str(),
                "-u", f"{user_id}",
            ]
        else:
            base_root_isolator = [
                PikaurConfig().misc.PrivilegeEscalationTool.get_str(),
                f"--user=#{user_id}",
            ]
            if preserve_envs:
                base_root_isolator.append(
                    "--preserve-env=" + ",".join(preserve_envs),
                )
            base_root_isolator.append(
                "--",
            )
    else:
        base_root_isolator = [
            "/usr/sbin/systemd-run",
            "--service-type=oneshot",
            "--pipe", "--wait", "--pty",
            "-p", "DynamicUser=yes",
            "-p", "CacheDirectory=pikaur",
            "-E", f"HOME={_UserTempRoot()}",
        ]
        if cwd is not None:
            base_root_isolator += ["-p", "WorkingDirectory=" + str(cwd.resolve())]
        for env_var_name in preserve_envs:
            base_root_isolator += ["-E", f"{env_var_name}={os.environ[env_var_name]}"]
        for env_var_name, env_var_value in env.items():
            base_root_isolator += ["-E", f"{env_var_name}={env_var_value}"]
    return base_root_isolator + cmd


def get_args_to_elevate_pikaur(original_args: list[str]) -> list[str]:
    args = parse_args()
    restart_args = original_args.copy()
    extra_args = [
        ("--pikaur-config", str(ConfigPath())),
    ]
    if not need_dynamic_users():
        extra_args += [
            ("--user-id", str(args.user_id or os.getuid())),
            ("--home-dir", str(args.home_dir or "") or Path.home().as_posix()),
        ]
        for flag, arg_key, env_key in (
            ("--xdg-cache-home", "xdg_cache_home", "XDG_CACHE_HOME"),
            ("--xdg-config-home", "xdg_config_home", "XDG_CONFIG_HOME"),
            ("--xdg-data-home", "xdg_data_home", "XDG_DATA_HOME"),
        ):
            arg_value = str(getattr(args, arg_key, None) or "")
            if value := (os.environ.get(env_key) or arg_value):
                extra_args += [
                    (flag, value),
                ]
    for flag, fallback in extra_args:
        config_overridden = max(
            arg.startswith(flag)
            for arg in restart_args
        )
        if not config_overridden:
            restart_args += [f"{flag}={fallback}"]
    return sudo(restart_args, preserve_env=get_envs_to_preserve())
