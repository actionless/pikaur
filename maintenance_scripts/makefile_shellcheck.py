#!/usr/bin/python

import os
import subprocess  # nosec B404
import sys
import tempfile

MAKEFILE = "./Makefile"
if len(sys.argv) > 1:
    MAKEFILE = sys.argv[1]

MAKE_SHELL = os.environ.get("MAKE_SHELL", "sh")
DEFAULT_ENCODING = "utf-8"


def get_targets() -> list[str]:
    targets = subprocess.check_output(
        args=(
            "make"
            " --dry-run"
            f' --makefile="{MAKEFILE}"'
            " --print-data-base"
            " --no-builtin-rules"
            " --no-builtin-variables"
            " | grep -E '^[^. ]+:' -o"
            # " | sort"
            " | sort -r"
            " | uniq"
            " | sed 's/:$//g'"
        ),
        shell=True,
        encoding=DEFAULT_ENCODING
    ).splitlines()

    targets.remove("Makefile")
    # # check it last:
    targets.remove("all")
    targets.append("all")
    return targets


def print_by_lines(text: str) -> None:
    for idx, line in enumerate(text.splitlines()):
        print(f"{idx+1}: {line}")


def print_error_in_target(target: str) -> None:
    print(
        f"\n{'-'*30}\n"
        f"ERROR in target `{target}`:"
        f"\n{'-'*30}"
    )


def main() -> None:
    print("Starting the check...")
    targets = get_targets()
    if "all" not in targets:
        print("ERROR: `all` target is not defined.")
        sys.exit(1)

    print("\nMake targets:")
    for target in targets:
        print(f"  {target}")
        try:
            make_result = subprocess.check_output(  # nosec B603
                args=[
                    "make",
                    "--dry-run",
                    f"--makefile={MAKEFILE}",
                    target,
                ],
                encoding=DEFAULT_ENCODING,
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as err:
            print_error_in_target(target)
            print_by_lines(err.output)
            sys.exit(1)
        with tempfile.NamedTemporaryFile("w", encoding=DEFAULT_ENCODING) as fobj:
            fobj.write(make_result)
            fobj.seek(0)
            try:
                subprocess.check_output(  # nosec B603
                    args=[
                        "shellcheck",
                        fobj.name,
                        f"--shell={MAKE_SHELL}",
                        "--color=always"
                    ],
                    encoding=DEFAULT_ENCODING,
                )
            except subprocess.CalledProcessError as err:
                print_error_in_target(target)
                print_by_lines(make_result)
                print(err.output.replace(fobj.name, f"{MAKEFILE}:{target}"))
                sys.exit(1)

    print("\n:: OK ::")


if __name__ == "__main__":
    main()
