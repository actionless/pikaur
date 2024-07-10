"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import gettext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Final

PIKAUR_NAME: "Final" = "pikaur"


class PikaurTranslation:

    translation: gettext.NullTranslations | None = None

    @classmethod
    def get(cls) -> gettext.NullTranslations:
        if not cls.translation:
            cls.translation = gettext.translation(PIKAUR_NAME, fallback=True)
        return cls.translation


def translate(msg: str) -> str:
    return PikaurTranslation.get().gettext(msg)


def translate_many(singular: str, plural: str, count: int) -> str:
    return PikaurTranslation.get().ngettext(singular, plural, count)


EXTRA_ERROR_MESSAGES: "Final[list[str]]" = [
    translate("Read damn arch-wiki before borking your computer:"),
    translate("(Also, don't report any issues to pikaur, if ure seeing this message)"),
]
