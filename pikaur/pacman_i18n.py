import gettext


class PacmanTranslation:

    translation: gettext.NullTranslations | None = None

    @classmethod
    def get(cls) -> gettext.NullTranslations:
        if not cls.translation:
            cls.translation = gettext.translation("pacman", fallback=True)
        return cls.translation


def _p(msg: str) -> str:
    return PacmanTranslation.get().gettext(msg)
