import datetime
import urllib.request
import urllib.error
import urllib.response
import xml.etree.ElementTree
from xml.etree.ElementTree import ElementTree
import os
from http.client import HTTPResponse
from html.parser import HTMLParser

from typing import TextIO, Union

from pikaur.config import CACHE_ROOT
from pikaur.pprint import color_line, format_paragraph, print_stdout


# from pikaur.pacman import


# TODO internationalization
# TODO get initial date (if dat-file not present) from last installed local package from the repo
# TODO get finally rid of those Travis warnings

class News(object):
    URL = 'https://www.archlinux.org'
    DIR = '/feeds/news/'

    def __init__(self) -> None:
        self._last_seen_news = self._get_last_seen_news()
        self._news_feed = self._get_rss_feed()

    def print_latest(self) -> None:
        if not isinstance(self._news_feed, ElementTree):
            return
        if not self._is_new(self._last_online_news(self._news_feed)):
            return
        news_entry: xml.etree.ElementTree.Element
        for news_entry in self._news_feed.iter('item'):
            child: xml.etree.ElementTree.Element
            for child in news_entry:
                if 'pubDate' in child.tag:
                    if self._is_new(str(child.text)):
                        self._print_one_entry(news_entry)
                    else:
                        # no more news
                        return

    def _get_rss_feed(self) -> Union[xml.etree.ElementTree.Element, None]:
        try:
            http_response: Union[HTTPResponse, urllib.response.addinfourl] = urllib.request.urlopen(
                self.URL + self.DIR
            )
        except urllib.error.URLError:
            print_stdout('Could not fetch archlinux.org news')
            return None
        str_response: str = ''
        for line in http_response:
            str_response += line.decode('UTF-8').strip()
        if not str_response:  # could not get data
            return None
        return xml.etree.ElementTree.fromstring(str_response)

    @staticmethod
    def _last_online_news(xml_feed: xml.etree.ElementTree.ElementTree) -> str:
        # we find the first 'pubDate' tag, which indicates
        # the most recent entry
        news_entry: xml.etree.ElementTree.Element
        for news_entry in xml_feed.iter('item'):
            child: xml.etree.ElementTree.Element
            for child in news_entry:
                if 'pubDate' in child.tag:
                    return str(child.text)
        # if we get to here, then something went really wrong
        # no valid news found
        return ''

    @staticmethod
    def _get_last_seen_news() -> str:
        filename: str = os.path.join(CACHE_ROOT, 'last_seen_news.dat')
        last_seen_fd: TextIO
        try:
            with open(filename) as last_seen_fd:
                return last_seen_fd.readline().strip()
        except IOError:
            # if file doesn't exist, this feature was run the first time
            # then we want to see all news from this moment on
            now: datetime.datetime = datetime.datetime.utcnow()
            time_formatted: str = now.strftime('%a, %d %b %Y %H:%M:%S +0000')
            try:
                with open(filename, 'w') as last_seen_fd:
                    last_seen_fd.write(time_formatted)
            except IOError:
                msg: str = 'Could not initialize {}'.format(filename)
                print_stdout(msg)
            return time_formatted

    def _is_new(self, last_online_news: str) -> bool:
        last_seen_news_date = datetime.datetime.strptime(
            self._last_seen_news, '%a, %d %b %Y %H:%M:%S %z'
        )
        if not last_online_news:
            raise ValueError('The news feed could not be received or parsed.')
        last_online_news_date: datetime.datetime = datetime.datetime.strptime(
            last_online_news, '%a, %d %b %Y %H:%M:%S %z'
        )
        return last_online_news_date > last_seen_news_date

    # noinspection PyUnboundLocalVariable
    @staticmethod
    def _print_one_entry(news_entry: xml.etree.ElementTree.Element) -> None:
        child: xml.etree.ElementTree.Element
        for child in news_entry:
            if 'title' in child.tag:
                title = str(child.text)
            if 'pubDate' in child.tag:
                pub_date = str(child.text)
            if 'description' in child.tag:
                description = str(child.text)
        print_stdout(
            color_line(title, 11) + ' (' + pub_date + ')'
        )
        print_stdout(
            format_paragraph(strip_tags(description))
        )
        print_stdout()


class MLStripper(HTMLParser):
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
    mlstripper = MLStripper()
    mlstripper.feed(html)
    return mlstripper.get_data()


if __name__ == '__main__':
    News().print_latest()
