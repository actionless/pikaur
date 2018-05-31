import datetime
import urllib.request
import urllib.error
import xml.etree.ElementTree
import os
from html.parser import HTMLParser

from pikaur.config import CACHE_ROOT
from pikaur.pprint import color_line, format_paragraph


# TODO type hints for variables
# TODO use coloring/bold font from pikaur.pprint
# TODO internationalization
# TODO get initial date (if dat-file not present) from last installed local package from the repo

class News(object):
    URL = 'https://www.archlinux.org'
    DIR = '/feeds/news/'

    def __init__(self):
        self._last_seen_news = self._get_last_seen_news()

    def check_news(self):
        rss_feed = self._get_rss_feed()
        if rss_feed is None:  # could not get data
            return
        xml_feed = xml.etree.ElementTree.fromstring(rss_feed)
        if self._is_new(self._last_online_news(xml_feed)):
            self._print_news(xml_feed)
        else:
            return

    def _get_rss_feed(self):
        try:
            http_response = urllib.request.urlopen(self.URL + self.DIR)
        except urllib.error.URLError:
            print('Could not fetch archlinux.org news')
            return None
        str_response = ''
        for line in http_response:
            str_response += line.decode('UTF-8').strip()
        return str_response

    @staticmethod
    def _last_online_news(xml_feed):
        # we find the first 'pubDate' tag, which indicates
        # the most recent entry
        for news_entry in xml_feed.getiterator('item'):
            for child in news_entry:
                if 'pubDate' in child.tag:
                    return child.text

    @staticmethod
    def _get_last_seen_news():
        filename = os.path.join(CACHE_ROOT, 'last_seen_news.dat')
        try:
            with open(filename) as fd:
                return fd.readline().strip()
        except IOError:
            # if file doesn't exist, this feature was run the first time
            # then we want to see all news from this moment on
            now = datetime.datetime.utcnow()
            time_formatted = now.strftime('%a, %d %b %Y %H:%M:%S +0000')
            try:
                with open(filename, 'w') as fd:
                    fd.write(time_formatted)
            except IOError:
                msg = 'Could not initialize {}'.format(filename)
                print(msg)
            return time_formatted

    def _is_new(self, last_online_news):
        last_seen_news_date = datetime.datetime.strptime(
            self._last_seen_news, '%a, %d %b %Y %H:%M:%S %z'
        )
        last_online_news_date = datetime.datetime.strptime(
            last_online_news, '%a, %d %b %Y %H:%M:%S %z'
        )
        return last_online_news_date > last_seen_news_date

    def _print_news(self, xml_feed):
        for news_entry in xml_feed.getiterator('item'):
            for child in news_entry:
                if 'pubDate' in child.tag:
                    if self._is_new(child.text):
                        self._print_one_entry(news_entry)
                    else:
                        # no more news
                        return

    # noinspection PyUnboundLocalVariable,PyPep8Naming
    @staticmethod
    def _print_one_entry(news_entry):
        for child in news_entry:
            if 'title' in child.tag:
                title = child.text
            if 'pubDate' in child.tag:
                pubDate = child.text
            if 'description' in child.tag:
                description = child.text
        print(color_line(title, 11) + ' (' + pubDate + ')')
        print(format_paragraph(strip_tags(description)))


class MLStripper(HTMLParser):
    def error(self, message):
        pass

    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.fed = []

    def handle_data(self, data):
        self.fed.append(data)

    def get_data(self):
        return ''.join(self.fed)


def strip_tags(html):
    mlstripper = MLStripper()
    mlstripper.feed(html)
    return mlstripper.get_data()


if __name__ == '__main__':
    news = News()
    news.check_news()
