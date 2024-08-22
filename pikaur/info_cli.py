from datetime import datetime
from multiprocessing.pool import ThreadPool
from unicodedata import east_asian_width

from .args import parse_args, reconstruct_args
from .aur import find_aur_packages, get_all_aur_names
from .config import DEFAULT_TIMEZONE
from .i18n import translate
from .pacman import get_pacman_command, refresh_pkg_db_if_needed
from .pacman_i18n import _p
from .pikaprint import ColorsHighlight, bold_line, color_line, print_stdout
from .spawn import spawn


def _info_packages_thread_repo() -> str | None:
    args = parse_args()
    proc = spawn(
        get_pacman_command() + reconstruct_args(args, ignore_args=["refresh"]) + args.positional,
    )
    return proc.stdout_text


def get_info_fields() -> dict[str, str]:
    return {
        "git_url": translate("AUR Git URL"),
        "web_url": translate("AUR Web URL"),
        # "aur_id": translate("id"),
        "name": translate("Name"),
        # packagebaseid=translate(""),
        "packagebase": translate("Package Base"),
        "version": translate("Version"),
        "desc": translate("Description"),
        "url": translate("URL"),
        "keywords": translate("Keywords"),
        "pkg_license": translate("Licenses"),
        "groups": translate("Groups"),
        "provides": translate("Provides"),
        "depends": translate("Depends On"),
        "optdepends": translate("Optional Deps"),
        "makedepends": translate("Make Deps"),
        "checkdepends": translate("Check Deps"),
        "conflicts": translate("Conflicts With"),
        "replaces": translate("Replaces"),
        "submitter": translate("Submitter"),
        "maintainer": translate("Maintainer"),
        "comaintainers": translate("Co-maintainers"),
        "numvotes": translate("Votes"),
        "popularity": translate("Popularity"),
        "firstsubmitted": translate("First Submitted"),
        "lastmodified": translate("Last Updated"),
        "outofdate": translate("Out-of-date"),
    }


def _decorate_repo_info_output(output: str) -> str:
    return output.replace(
        _p("None"), color_line(_p("None"), ColorsHighlight.black),
    )


def _decorate_aur_info_output(output: str) -> str:
    return output.replace(
        translate("None"), color_line(translate("None"), ColorsHighlight.black),
    )


def cli_info_packages() -> None:
    refresh_pkg_db_if_needed()

    args = parse_args()
    aur_pkg_names = args.positional or get_all_aur_names()
    with ThreadPool() as pool:
        aur_thread = pool.apply_async(find_aur_packages, (aur_pkg_names, ))
        repo_thread = pool.apply_async(_info_packages_thread_repo, ())
        pool.close()
        pool.join()
        repo_result = repo_thread.get()
        aur_result = aur_thread.get()

    if repo_result:
        print_stdout(_decorate_repo_info_output(repo_result), end="")

    aur_pkgs = aur_result[0]
    num_found = len(aur_pkgs)
    info_fields = get_info_fields()
    longest_field_length = max(len(field) for field in info_fields.values())
    for i, aur_pkg in enumerate(aur_pkgs):
        pkg_info_lines = []
        for key, display_name in info_fields.items():
            value = getattr(aur_pkg, key, None)
            if key in {"firstsubmitted", "lastmodified", "outofdate"} and value:
                value = datetime.fromtimestamp(value, tz=DEFAULT_TIMEZONE).strftime("%c")
            elif isinstance(value, list):
                value = ", ".join(value) or translate("None")
            key_display = bold_line(_rightpad(display_name, longest_field_length + 1))
            pkg_info_lines.append(f"{key_display}: {value}")
        print_stdout(
            _decorate_aur_info_output("\n".join(pkg_info_lines)) +
            ("\n" if i + 1 < num_found else ""),
        )


def _rightpad(text: str, num: int) -> str:
    space = num
    for i in text:
        if east_asian_width(i) in {"F", "W"}:
            space -= 2
        else:
            space -= 1
    return text + " " * space
