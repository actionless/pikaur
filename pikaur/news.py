import datetime
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import os
from html.parser import HTMLParser

from pikaur.config import CACHE_ROOT



class News():
    URL = 'https://www.archlinux.org'
    DIR = '/feeds/news/'
    def __init__(self):
        self._last_seen_news = self._get_last_seen_news()

    def check_news(self):
        rss_feed = self._get_rss_feed()
        if rss_feed is None:  # could not get data
            return
        xml_feed = ET.fromstring(rss_feed)
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

    def _last_online_news(self, xml_feed):
        # we find the first 'pubDate' tag, which indicates
        # the most recent entry
        for news_entry in xml_feed.getiterator('item'):
            for child in news_entry:
                if 'pubDate' in child.tag:
                    return child.text

    def _get_last_seen_news(self):
        filename = os.path.join(CACHE_ROOT, 'last_seen_news.dat')
        try:
            with open(filename) as fd:
                return fd.readline().strip()
        except IOError:
            # if file doesn't exist, this feature was run the first time
            # then we want to see all news from this moment on
            t = datetime.datetime.utcnow()
            time_formatted = t.strftime('%a, %d %b %Y %H:%M:%S +0000')
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
        if last_online_news_date > last_seen_news_date:
            return True
        else:
            return False

    def _print_news(self, xml_feed):
        for news_entry in xml_feed.getiterator('item'):
            for child in news_entry:
                if 'pubDate' in child.tag:
                    if self._is_new(child.text):
                        self._print_one_entry(news_entry)
                    else:
                        # no more news
                        return

    def _print_one_entry(self, news_entry):
        for child in news_entry:
            if 'title' in child.tag:
                title = child.text
            if 'pubDate' in child.tag:
                pubDate = child.text
            if 'description' in child.tag:
                description = child.text
        print(title + ' (' + pubDate + ')')
        print(text_wrap(strip_tags(description)))

class MLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()

def text_wrap(text, max_width=80):
    # we remember all spaces in can_split, and all line breaks in breaks.
    # if we hit max_width since the most recent break, we add a newline at the
    # the value saved in breaks.
    breaks = [0]
    can_split = 0
    for pos, char in enumerate(text):
        if char == ' ':
            can_split = pos
        if pos - breaks[-1] > max_width:
            breaks.append(can_split)
        pos += 1
    breaks.append(len(text))
    new_text = ''
    for i in range(len(breaks) - 1):
        start = breaks[i]
        end = breaks[i+1]
        new_text += text[start:end].strip() + '\n'
    return new_text


if __name__ == '__main__':
    news = News()
    news.check_news()