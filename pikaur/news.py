"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""

import datetime
from html.parser import HTMLParser
from typing import TYPE_CHECKING

try:
    from defusedxml.ElementTree import fromstring  # type: ignore[import-untyped]
except ModuleNotFoundError:
    from xml.etree.ElementTree import fromstring  # nosec B405  # noqa: S405

from .config import DEFAULT_TIMEZONE, CacheRoot, PikaurConfig
from .i18n import translate
from .logging_extras import create_logger
from .os_utils import open_file
from .pacman import PackageDB
from .pikaprint import (
    BOLD_RESET,
    BOLD_START,
    COLOR_RESET,
    PADDING,
    ColorsHighlight,
    bold_line,
    color_line,
    color_start,
    format_paragraph,
    get_term_width,
    print_error,
    print_stdout,
)
from .urllib_helper import get_unicode_from_url

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Final, TextIO
    from xml.etree.ElementTree import Element  # nosec B405  # noqa: S405


DT_FORMAT: "Final" = "%a, %d %b %Y %H:%M:%S %z"

logger = create_logger("news")


class ArchNewsMarkup:
    PUBLICATION_DATE: "Final" = "pubDate"
    TITLE: "Final" = "title"
    DESCRIPTION: "Final" = "description"


class News:
    url: str
    cache_file: "Path"
    _news_feed: "Element | None"
    _news_entry_to_update_last_seen_date: "Element | None"
    any_news: bool = False

    def __init__(self) -> None:
        self.url = PikaurConfig().network.NewsUrl.get_str()
        self.cache_file = CacheRoot() / "last_seen_news.dat"
        self._news_feed = None
        self._news_entry_to_update_last_seen_date = None
        logger.debug("init")

    def print_news(self) -> None:
        logger.debug("print")
        news_entry: Element
        if self._news_feed is None:
            print_error(translate("Could not fetch archlinux.org news"))
            return
        first_news = True
        for news_entry in self._news_feed.iter("item"):
            child: Element
            for child in news_entry:
                if ArchNewsMarkup.PUBLICATION_DATE in child.tag:
                    if self._is_new(str(child.text)):
                        if first_news:
                            print_stdout(
                                "\n" +
                                color_line(
                                    translate("There is news from archlinux.org!"),
                                    ColorsHighlight.red,
                                ) +
                                "\n",
                            )
                        self._print_one_entry(news_entry)
                        # news are in inverse chronological order (newest first).
                        # if there is something to print, we save this date
                        # in our cache
                        if first_news:
                            first_news = False
                            self._news_entry_to_update_last_seen_date = news_entry
                            self.any_news = True
                    else:
                        # no more news
                        return

    def mark_as_read(self) -> None:
        if self._news_entry_to_update_last_seen_date:
            self._update_last_seen_news(self._news_entry_to_update_last_seen_date)
        self.any_news = False

    def fetch_latest(self) -> None:
        logger.debug("fetch_latest")
        str_response = get_unicode_from_url(self.url, optional=True)
        if not str_response:
            print_error(translate("Could not fetch archlinux.org news"))
            return
        self._news_feed = fromstring(str_response)  # nosec B314  # noqa: S314

    def _get_last_seen_news_date(self) -> datetime.datetime:
        last_seen_fd: TextIO
        try:
            logger.debug("loading date from {}", self.cache_file)
            with open_file(self.cache_file) as last_seen_fd:
                file_data = last_seen_fd.readline().strip()
                parsed_date = datetime.datetime.strptime(  # noqa: DTZ007
                    file_data, DT_FORMAT,
                )
                logger.debug("data: {}, parsed: {}", file_data, parsed_date)
                return parsed_date
        except (OSError, ValueError):
            # if file doesn't exist or corrupted,
            # this feature was run the first time
            # then we get take the date from the last installed package:
            last_pkg_date: datetime.datetime = datetime.datetime.fromtimestamp(
                PackageDB.get_last_installed_package_date(),
                tz=DEFAULT_TIMEZONE,
            )
            time_formatted: str = last_pkg_date.strftime(DT_FORMAT)
            try:
                with open_file(self.cache_file, "w") as last_seen_fd:
                    last_seen_fd.write(time_formatted)
            except OSError:
                print_error(translate("Could not initialize {}").format(self.cache_file))
            return last_pkg_date

    def _is_new(self, last_online_news: str) -> bool:
        if not last_online_news:
            print_error(translate("The news feed could not be received or parsed."))
            return False
        last_online_news_date: datetime.datetime = datetime.datetime.strptime(  # noqa: DTZ007
            last_online_news, DT_FORMAT,
        )
        last_seen_news_date = self._get_last_seen_news_date()
        logger.debug(
            "Arch News Date: {}, Last-seen date: {}",
            last_online_news_date, last_seen_news_date,
        )
        return last_online_news_date > last_seen_news_date

    @staticmethod
    def _print_one_entry(news_entry: "Element") -> None:
        child: Element
        title = pub_date = description = ""
        for child in news_entry:
            if ArchNewsMarkup.TITLE in child.tag:
                title = str(child.text)
            if ArchNewsMarkup.PUBLICATION_DATE in child.tag:
                pub_date = str(child.text)
            if ArchNewsMarkup.DESCRIPTION in child.tag:
                description = str(child.text)
        print_stdout(
            color_line(title, ColorsHighlight.cyan) +
            " (" + bold_line(pub_date) + ")",
        )
        print_stdout(
            "\n".join(format_paragraph(line) for line in strip_tags(description).splitlines()),
        )
        print_stdout()

    def _update_last_seen_news(self, news_entry: "Element") -> None:
        child: Element
        for child in news_entry:
            if ArchNewsMarkup.PUBLICATION_DATE in child.tag:
                pub_date = str(child.text)
                break
        try:
            with open_file(self.cache_file, "w") as last_seen_fd:
                last_seen_fd.write(pub_date)
        except OSError:
            print_error(translate("Could not update {}").format(self.cache_file))


class MLStripper(HTMLParser):
    """HTMLParser optimized for terminal output."""

    last_href: str | None = None
    last_data: str | None = None

    def error(self, message: object) -> None:
        pass

    def __init__(self) -> None:
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.fed: list[str] = []

    def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag in {"strong", "em"}:
            self.fed.append(BOLD_START)
        elif tag == "h2":
            self.fed.append("\n")
        elif tag == "hr":
            self.fed.append("-" * (get_term_width() - PADDING * 2))
        elif tag == "a":
            self.last_href = dict(attrs).get("href")
        elif tag == "li":
            self.fed.append("- ")

        color = None
        if tag == "code":
            color = ColorsHighlight.green
        elif tag == "blockquote":
            color = ColorsHighlight.yellow
        elif tag == "a":
            color = ColorsHighlight.cyan
        elif tag == "h2":
            color = ColorsHighlight.purple
        elif tag not in {"strong", "em", "h2", "hr", "li", "ul", "p"}:
            logger.debug("Encountered unknown start tag: {}", tag)
        if color is not None:
            self.fed.append(color_start(color))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"code", "blockquote", "a", "h2"}:
            self.fed.append(COLOR_RESET)
        elif tag in {"strong", "em"}:
            self.fed.append(BOLD_RESET)
        if (tag == "a") and self.last_href:
            if self.last_data != self.last_href:
                self.fed.append(f": {color_line(self.last_href, ColorsHighlight.blue)} ")
            else:
                self.fed.append(" ")

    def handle_data(self, data: str) -> None:
        self.last_data = data
        self.fed.append(data)

    def get_data(self) -> str:
        return "".join(self.fed)


def strip_tags(html: str) -> str:
    """Removes HTML tags from a string, returns the plain string."""
    mlstripper = MLStripper()
    mlstripper.feed(html)
    return mlstripper.get_data()
