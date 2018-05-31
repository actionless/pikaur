import datetime
import urllib.request
import urllib.error
import xml.etree.ElementTree
import os
from http.client import HTTPResponse
from html.parser import HTMLParser

from typing import TextIO

from pikaur.config import CACHE_ROOT
import pikaur.pprint


# TODO internationalization
# TODO get initial date (if dat-file not present) from last installed local package from the repo

class News(object):
    _last_seen_news: str
    URL = 'https://www.archlinux.org'
    DIR = '/feeds/news/'

    def __init__(self) -> None:
        self._last_seen_news = self._get_last_seen_news()

    def check_news(self) -> None:
        rss_feed: str = self._get_rss_feed()
        if len(rss_feed) == 0:  # could not get data
            return
        xml_feed: xml.etree.ElementTree.ElementTree = \
            xml.etree.ElementTree.fromstring(rss_feed)
        if self._is_new(self._last_online_news(xml_feed)):
            self._print_news(xml_feed)

    def _get_rss_feed(self):
        try:
            http_response: HTTPResponse = urllib.request.urlopen(
                self.URL + self.DIR
            )
        except urllib.error.URLError:
            pikaur.pprint.print_stdout('Could not fetch archlinux.org news')
            return ''
        str_response: str = ''
        for line in http_response:
            str_response += line.decode('UTF-8').strip()
        return str_response

    @staticmethod
    def _last_online_news(xml_feed: xml.etree.ElementTree.ElementTree) -> str:
        # we find the first 'pubDate' tag, which indicates
        # the most recent entry
        news_entry: xml.etree.ElementTree.Element
        for news_entry in xml_feed.iter('item'):
            child: xml.etree.ElementTree.Element
            for child in news_entry:
                if 'pubDate' in child.tag:
                    return child.text
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
                pikaur.pprint.print_stdout(msg)
            return time_formatted

    def _is_new(self, last_online_news: str) -> bool:
        last_seen_news_date = datetime.datetime.strptime(
            self._last_seen_news, '%a, %d %b %Y %H:%M:%S %z'
        )
        if len(last_online_news) == 0:
            raise ValueError('The news feed could not be received or parsed.')
        last_online_news_date: datetime = datetime.datetime.strptime(
            last_online_news, '%a, %d %b %Y %H:%M:%S %z'
        )
        return last_online_news_date > last_seen_news_date

    def _print_news(self, xml_feed: xml.etree.ElementTree.ElementTree):
        news_entry: xml.etree.ElementTree.Element
        for news_entry in xml_feed.iter('item'):
            child: xml.etree.ElementTree.Element
            for child in news_entry:
                if 'pubDate' in child.tag:
                    if self._is_new(child.text):
                        self._print_one_entry(news_entry)
                    else:
                        # no more news
                        return

    # noinspection PyUnboundLocalVariable,PyPep8Naming
    @staticmethod
    def _print_one_entry(news_entry: xml.etree.ElementTree.Element) -> None:
        child: xml.etree.ElementTree.Element
        for child in news_entry:
            if 'title' in child.tag:
                title: str = child.text
            if 'pubDate' in child.tag:
                pub_date: str = child.text
            if 'description' in child.tag:
                description: str = child.text
        pikaur.pprint.print_stdout(
            pikaur.pprint.color_line(title, 11) + ' (' + pub_date + ')'
        )
        pikaur.pprint.print_stdout(
            pikaur.pprint.format_paragraph(strip_tags(description))
        )


class MLStripper(HTMLParser):
    def error(self, message: object) -> None:
        pass

    def __init__(self) -> None:
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.fed = []

    def handle_data(self, data: object) -> None:
        self.fed.append(data)

    def get_data(self) -> str:
        return ''.join(self.fed)


def strip_tags(html: object) -> str:
    mlstripper = MLStripper()
    mlstripper.feed(html)
    return mlstripper.get_data()


if __name__ == '__main__':
    News().check_news()
