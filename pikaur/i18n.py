"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import gettext


class PikaurTranslation():

    translation: gettext.NullTranslations | None = None

    @classmethod
    def get(cls) -> gettext.NullTranslations:
        if not cls.translation:
            cls.translation = gettext.translation("pikaur", fallback=True)
        return cls.translation


def translate(msg: str) -> str:
    return PikaurTranslation.get().gettext(msg)


def translate_many(singular: str, plural: str, count: int) -> str:
    return PikaurTranslation.get().ngettext(singular, plural, count)
