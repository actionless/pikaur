import importlib
import inspect
import pkgutil
import sys

from pikaur.exceptions import SysExit
from pikaur.pikaprint import print_error, print_stdout
from pikaur.prompt import NotANumberInputError, get_multiple_numbers_input


def main() -> None:
    parent_module = importlib.import_module(__package__)
    print("HI! 🖖😼")

    options = {}
    for _loader, module_name, _is_pkg in pkgutil.walk_packages(
            parent_module.__path__, parent_module.__name__ + ".",
    ):
        module = importlib.import_module(module_name)
        methods = inspect.getmembers(module)
        method_names = [n for n, m in methods]
        if "main" in method_names:
            options[module_name] = module.main

    numerated_options = list(options)
    for idx, module_name in enumerate(numerated_options):
        print_stdout(f"{idx}: {module_name}")
    try:
        answers = get_multiple_numbers_input(answers=list(range(len(options))))
    except NotANumberInputError:
        print_error("Only numbers allowed")
        sys.exit(1)
    except (SysExit, KeyboardInterrupt):
        sys.exit(0)
    if len(answers) > 1:
        print_error("Only one answer allowed")
        sys.exit(1)
    if len(answers) < 1:
        main()
        sys.exit(0)
    options[numerated_options[answers[0]]]()


if __name__ == "__main__":
    main()
