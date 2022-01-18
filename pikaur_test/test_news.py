""" This file is licensed under GPLv3, see https://www.gnu.org/licenses/ """
import os
from unittest import TestCase

from pikaur_test.helpers import InterceptSysOutput

from pikaur.news import News
from pikaur.core import open_file


class NewsTest(TestCase):

    def test_news(self):
        if os.path.exists(News.CACHE_FILE):
            os.remove(News.CACHE_FILE)
        news = News()
        news.fetch_latest()

        with open_file(News.CACHE_FILE, 'w') as news_fd:
            news_fd.write("Fri, 03 May 2018 20:27:33 +0000")

        intercepted: InterceptSysOutput
        with InterceptSysOutput() as _intercepted:
            news = News()
            news.fetch_latest()
            news.print_news()
            intercepted = _intercepted

        self.assertGreater(len(intercepted.stdout_text.splitlines()), 4)
