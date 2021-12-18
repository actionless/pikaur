""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import gettext


TRANSLATION = gettext.translation('pikaur', fallback=True)


def translate(msg: str) -> str:
    return TRANSLATION.gettext(msg)


def translate_many(singular: str, plural: str, count: int) -> str:
    return TRANSLATION.ngettext(singular, plural, count)
