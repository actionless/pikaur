""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """

import datetime
import os
from html.parser import HTMLParser
from typing import TextIO, Union, TYPE_CHECKING

try:
    from defusedxml.ElementTree import fromstring  # type: ignore[import]
except ModuleNotFoundError:
    from xml.etree.ElementTree import fromstring  # nosec B405

from .i18n import translate
from .config import CACHE_ROOT, PikaurConfig
from .pprint import (
    color_line, format_paragraph, print_stdout, print_error, bold_line,
    create_debug_logger, ColorsHighlight,
)
from .pacman import PackageDB
from .urllib import get_unicode_from_url
from .core import open_file

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element  # noqa  # nosec B405


DT_FORMAT = '%a, %d %b %Y %H:%M:%S %z'

_debug = create_debug_logger('news')


class News:
    URL = PikaurConfig().network.NewsUrl.get_str()
    CACHE_FILE = os.path.join(CACHE_ROOT, 'last_seen_news.dat')
    _news_feed: Union['Element', None]

    def __init__(self) -> None:
        self._news_feed = None
        _debug('init')

    def print_news(self) -> None:
        _debug('print')
        if self._news_feed is None:
            print_error(translate('Could not fetch archlinux.org news'))
            return
        news_entry: 'Element'
        first_news = True
        news_entry_to_update_last_seen_date = None
        try:  # pylint: disable=too-many-nested-blocks
            for news_entry in self._news_feed.iter('item'):
                child: 'Element'
                for child in news_entry:
                    if 'pubDate' in child.tag:
                        if self._is_new(str(child.text)):
                            if first_news:
                                print_stdout(
                                    '\n' +
                                    color_line(
                                        translate('There is news from archlinux.org!'),
                                        ColorsHighlight.red
                                    ) +
                                    '\n'
                                )
                            self._print_one_entry(news_entry)
                            # news are in inverse chronological order (newest first).
                            # if there is something to print, we save this date
                            # in our cache
                            if first_news:
                                first_news = False
                                news_entry_to_update_last_seen_date = news_entry
                        else:
                            # no more news
                            return
        finally:
            if news_entry_to_update_last_seen_date:
                self._update_last_seen_news(news_entry_to_update_last_seen_date)

    def fetch_latest(self) -> None:
        _debug('fetch_latest')
        str_response = get_unicode_from_url(self.URL, optional=True)
        if not str_response:
            print_error(translate('Could not fetch archlinux.org news'))
            return
        self._news_feed = fromstring(str_response)  # nosec B314

    def _get_last_seen_news_date(self) -> datetime.datetime:
        last_seen_fd: TextIO
        try:
            _debug(f"loading date from {self.CACHE_FILE}")
            with open_file(self.CACHE_FILE) as last_seen_fd:
                file_data = last_seen_fd.readline().strip()
                parsed_date = datetime.datetime.strptime(
                    file_data, DT_FORMAT
                )
                _debug(f"{file_data=}, {parsed_date=}")
                return parsed_date
        except (IOError, ValueError):
            # if file doesn't exist or corrupted,
            # this feature was run the first time
            # then we get take the date from the last installed package:
            last_pkg_date: datetime.datetime = datetime.datetime.fromtimestamp(
                PackageDB.get_last_installed_package_date()
            )
            last_pkg_date = last_pkg_date.replace(
                tzinfo=datetime.datetime.now().astimezone().tzinfo
            )
            time_formatted: str = last_pkg_date.strftime(DT_FORMAT)
            try:
                with open_file(self.CACHE_FILE, 'w') as last_seen_fd:
                    last_seen_fd.write(time_formatted)
            except IOError:
                print_error(translate('Could not initialize {}').format(self.CACHE_FILE))
            return last_pkg_date

    def _is_new(self, last_online_news: str) -> bool:
        if not last_online_news:
            print_error(translate('The news feed could not be received or parsed.'))
            return False
        last_online_news_date: datetime.datetime = datetime.datetime.strptime(
            last_online_news, DT_FORMAT
        )
        last_seen_news_date = self._get_last_seen_news_date()
        _debug(f'is_new, {last_online_news_date=}, {last_seen_news_date=}')
        return last_online_news_date > last_seen_news_date

    @staticmethod
    def _print_one_entry(news_entry: 'Element') -> None:
        child: 'Element'
        for child in news_entry:
            if 'title' in child.tag:
                title = str(child.text)
            if 'pubDate' in child.tag:
                pub_date = str(child.text)
            if 'description' in child.tag:
                description = str(child.text)
        print_stdout(
            color_line(title, ColorsHighlight.cyan) +
            ' (' + bold_line(pub_date) + ')'
        )
        print_stdout(
            format_paragraph(strip_tags(description))
        )
        print_stdout()

    def _update_last_seen_news(self, news_entry: 'Element') -> None:
        child: 'Element'
        for child in news_entry:
            if 'pubDate' in child.tag:
                pub_date = str(child.text)
                break
        try:
            with open_file(self.CACHE_FILE, 'w') as last_seen_fd:
                last_seen_fd.write(pub_date)
        except IOError:
            print_error(translate('Could not update {}').format(self.CACHE_FILE))


class MLStripper(HTMLParser):
    """
    HTMLParser that only removes HTML statements
    """
    def error(self, message: object) -> None:
        pass

    def __init__(self) -> None:
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.fed: list = []

    def handle_data(self, data: object) -> None:
        self.fed.append(data)

    def get_data(self) -> str:
        return ''.join(self.fed)


def strip_tags(html: str) -> str:
    """
    removes HTML tags from a string, returns the plain string
    """
    mlstripper = MLStripper()
    mlstripper.feed(html)
    return mlstripper.get_data()
