import gettext

TRANSLATION = gettext.translation('pikaur', fallback=True)


def _(msg):
    return TRANSLATION.gettext(msg)


def _n(singular, plural, count):
    return TRANSLATION.ngettext(singular, plural, count)
