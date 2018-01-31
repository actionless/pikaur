#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

from pikaur.main import main, color_line


if __name__ == '__main__':
    if os.getuid() == 0:
        print("{} {}".format(
            color_line('::', 9),
            "Don't run me as root."
        ))
        sys.exit(1)
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
