import sys
from dataclasses import dataclass
from typing import cast

import pyalpm

from pikaur.pacman import PackageDB
from pikaur.pikaprint import ColorsHighlight, color_line, format_paragraph, get_term_width
from pikaur.pikatypes import AURPackageInfo
from pikaur.pikatypes import InstallInfo as InstallInfoOld
from pikaur.print_department import pretty_format_upgradeable


@dataclass(eq=False, kw_only=True)
class InstallInfo(InstallInfoOld):
    # @TODO: move it to the main module?
    name: str = ""
    new_version: str = ""
    current_version: str = ""

    def __post_init__(self) -> None:
        pkg_type = (
            "aur"
            if isinstance(self.package, AURPackageInfo)
            else (
                "local"
                if self.package.db.name == "local"
                else "repo"
            )
        )
        if pkg_type == "local":
            if not self.current_version:
                self.current_version = self.package.version
            if self.required_by_installed is None:
                self.required_by_installed = \
                    cast("pyalpm.Package", self.package).compute_requiredby()
            if self.optional_for_installed is None:
                self.optional_for_installed = \
                    cast("pyalpm.Package", self.package).compute_optionalfor()
            if self.installed_as_dependency is None:
                self.installed_as_dependency = \
                    cast(bool, cast("pyalpm.Package", self.package).reason)
        if not self.name:
            self.name = self.package.name
        if (
            (not self.new_version)
            and (pkg_type in {"aur", "repo"})
        ):
            self.new_version = self.package.version
        if not self.description:
            self.description = self.package.desc


@dataclass
class StackItem:
    item_type: str  # 'pkg' or 'title'
    content: str  # Package name or title text
    level: int  # Current level in the dependency tree


def compute_padding(
        current_level: int, global_padding: int = 1, branch_padding: int = 2,
) -> tuple[str, str]:
    """Compute padding for levels and descriptions."""
    if current_level:
        desc_spaces = (
            " " * global_padding + (" |" + " " * branch_padding) * current_level
        )
        level_spaces = (
            " " * global_padding + (" |" + " " * branch_padding) * (current_level - 1)
            + (" |" + "-" * branch_padding)
        )
    else:
        desc_spaces = level_spaces = (
            " " * global_padding
        )
    return level_spaces, desc_spaces


def print_package_info(
    install_info: InstallInfo, level_spaces: str, desc_spaces: str, *, description: bool,
) -> None:
    """Print formatted information for a given package."""
    output = "\n".join(
        (
            level_spaces
            + pretty_format_upgradeable(
                [install_info],
                required_by_installed=True,
                template=(
                    # "{pkg_name}{spacing}"
                    "{pkg_name}"
                    " {current_version}{spacing2}"
                    # "{version_separator}{new_version}{spacing3}"
                    "{pkg_size}{days_old}{out_of_date}"
                    "{required_by_installed}"
                    "{verbose}"
                ),
            ).splitlines()[0],
            *(
                [
                    "\n".join(
                        desc_spaces + line
                        for line in format_paragraph(
                            install_info.description or "",
                            padding=2,
                            width=get_term_width() - len(level_spaces),
                        ).splitlines()
                    ),
                ]
                if description
                else []
            ),
        ),
    )
    print(output)


def add_dependencies_to_stack(
        stack: list[StackItem], install_info: InstallInfo, current_level: int,
) -> None:
    """Add package dependencies to the processing stack."""
    next_level = current_level + 1

    if install_info.optional_for_installed:
        stack.extend([
            StackItem("pkg", dep_name, next_level)
            for dep_name in reversed(install_info.optional_for_installed)
        ])
        stack.append(
            StackItem("title", color_line(" optional for:", ColorsHighlight.purple), next_level),
        )

    if install_info.required_by_installed:
        stack.extend([
            StackItem("pkg", dep_name, next_level)
            for dep_name in reversed(install_info.required_by_installed)
        ])
        stack.append(
            StackItem("title", color_line(" required by:", ColorsHighlight.cyan), next_level),
        )


def process_stack_item(
        item: StackItem, already_processed: set[str],
        local_pkgs_dict: dict[str, pyalpm.Package],
        max_level: int, stack: list[StackItem],
        *, description: bool,
) -> None:
    """Process a single item from the stack."""
    global_padding = 1
    branch_padding = 2

    if item.item_type == "pkg":
        level_spaces, desc_spaces = compute_padding(item.level, global_padding, branch_padding)
        pkg = local_pkgs_dict[item.content]
        install_info = InstallInfo(package=pkg)

        if item.content in already_processed:
            print_package_info(install_info, level_spaces, desc_spaces, description=False)
            print(desc_spaces + "^")
            return

        print_package_info(install_info, level_spaces, desc_spaces, description=description)
        already_processed.add(item.content)

        if item.level < max_level:
            add_dependencies_to_stack(stack, install_info, item.level)

    elif item.item_type == "title":
        _level_spaces, desc_spaces = compute_padding(item.level - 1, global_padding, branch_padding)
        print(desc_spaces + item.content)

    else:
        raise NotImplementedError


def cli(pkgname: str, max_level: int = 2, *, description: bool = True) -> None:
    """Entry point for the CLI."""
    local_pkgs_dict = PackageDB.get_local_dict()

    already_processed: set[str] = set()
    stack = [StackItem("pkg", pkgname, 0)]

    while stack:
        current_item = stack.pop()
        process_stack_item(
            current_item, already_processed, local_pkgs_dict, max_level, stack,
            description=description,
        )


if __name__ == "__main__":
    cli(pkgname=sys.argv[1], max_level=2)
