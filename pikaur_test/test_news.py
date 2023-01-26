"""Licensed under GPLv3, see https://www.gnu.org/licenses/"""
# mypy: disable-error-code=no-untyped-def

from unittest import TestCase

from pikaur.core import open_file
from pikaur.news import News
from pikaur_test.helpers import InterceptSysOutput


class NewsTest(TestCase):

    def test_news(self):
        if News.CACHE_FILE.exists():
            News.CACHE_FILE.unlink()
        news = News()
        news.fetch_latest()

        with open_file(News.CACHE_FILE, "w") as news_fd:
            news_fd.write("Fri, 03 May 2018 20:27:33 +0000")

        with InterceptSysOutput() as intercepted:
            news = News()
            news.fetch_latest()
            news.print_news()

        self.assertGreater(len(intercepted.stdout_text.splitlines()), 4)
