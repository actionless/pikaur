from datetime import datetime
from multiprocessing.pool import ThreadPool
from unicodedata import east_asian_width

from .i18n import translate
from .pacman_i18n import _p
from .aur import find_aur_packages, get_all_aur_names
from .args import parse_args, reconstruct_args
from .core import spawn
from .pacman import get_pacman_command, refresh_pkg_db_if_needed
from .pprint import bold_line, color_line, ColorsHighlight


def _info_packages_thread_repo() -> str:
    args = parse_args()
    return spawn(
        get_pacman_command() + reconstruct_args(args, ignore_args=['refresh']) + args.positional
    ).stdout_text


INFO_FIELDS = dict(
    git_url=translate("AUR Git URL"),
    # id=translate("id"),
    name=translate("Name"),
    # packagebaseid=translate(""),
    packagebase=translate("Package Base"),
    version=translate("Version"),
    desc=translate("Description"),
    url=translate("URL"),
    keywords=translate("Keywords"),
    license=translate("Licenses"),
    groups=translate("Groups"),
    provides=translate("Provides"),
    depends=translate("Depends On"),
    optdepends=translate("Optional Deps"),
    makedepends=translate("Make Deps"),
    checkdepends=translate("Check Deps"),
    conflicts=translate("Conflicts With"),
    replaces=translate("Replaces"),
    maintainer=translate("Maintainer"),
    numvotes=translate("Votes"),
    popularity=translate("Popularity"),
    firstsubmitted=translate("First Submitted"),
    lastmodified=translate("Last Updated"),
    outofdate=translate("Out-of-date"),
)


def _decorate_repo_info_output(output: str) -> str:
    return output.replace(
        _p('None'), color_line(_p('None'), ColorsHighlight.black)
    )


def _decorate_aur_info_output(output: str) -> str:
    return output.replace(
        translate('None'), color_line(translate('None'), ColorsHighlight.black)
    )


def cli_info_packages() -> None:  # pylint: disable=too-many-locals
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
        print(_decorate_repo_info_output(repo_result), end='')

    aur_pkgs = aur_result[0]
    num_found = len(aur_pkgs)
    longest_field_length = max(len(field) for field in INFO_FIELDS.values())
    for i, aur_pkg in enumerate(aur_pkgs):
        pkg_info_lines = []
        for key, display_name in INFO_FIELDS.items():
            value = getattr(aur_pkg, key, None)
            if key in ['firstsubmitted', 'lastmodified', 'outofdate'] and value:
                value = datetime.fromtimestamp(value).strftime('%c')
            elif isinstance(value, list):
                value = ', '.join(value) or translate("None")
            key_display = bold_line(_rightpad(display_name, longest_field_length + 1))
            pkg_info_lines.append(f'{key_display}: {value}')
        print(
            _decorate_aur_info_output('\n'.join(pkg_info_lines)) +
            ('\n' if i + 1 < num_found else '')
        )


def _rightpad(text: str, num: int) -> str:
    space = num
    for i in text:
        if east_asian_width(i) in ["F", "W", ]:
            space -= 2
        else:
            space -= 1
    return text + " " * space
