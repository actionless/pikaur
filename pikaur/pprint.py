import shutil


def color_line(line, color_number):
    result = ''
    if color_number >= 8:
        result += "\033[1m"
        color_number -= 8
    result += f"\033[03{color_number}m{line}"
    # reset font:
    result += "\033[0m"
    return result


def format_paragraph(line):
    padding = 4
    term_width = shutil.get_terminal_size((80, 80)).columns
    max_line_width = term_width - padding * 2

    result = []
    current_line = []
    line_length = 0
    for word in line.split():
        if len(word) + line_length > max_line_width:
            result.append(current_line)
            current_line = []
            line_length = 0
        current_line.append(word)
        line_length += len(word) + 1
    result.append(current_line)

    return '\n'.join([
        ' '.join(
            [(padding-1)*' ', ] +
            words +
            [(padding-1)*' ', ],
        )
        for words in result
    ])


def print_not_found_packages(not_found_packages):
    print("{} {}".format(
        color_line(':: warning:', 11),
        color_line('Following packages can not be found in AUR:', 15),
    ))
    for package in not_found_packages:
        print(format_paragraph(package))


def pretty_print_upgradeable(packages_updates, ignore=None):
    ignore = ignore or []

    def pretty_format(self):
        return '{} {} -> {}'.format(
            color_line(self.pkg_name, 15),
            color_line(self.current_version, 10),
            color_line(self.aur_version, 10)
        )

    print('\n'.join([
        format_paragraph(pretty_format(pkg_update))
        for pkg_update in packages_updates
        if pkg_update.pkg_name not in ignore
    ]))


def print_upgradeable(packages_updates):
    print('\n'.join([
        pkg_update.pkg_name
        for pkg_update in packages_updates
    ]))
