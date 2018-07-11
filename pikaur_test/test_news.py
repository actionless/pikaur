import os

from pikaur_test.helpers import InterceptSysOutput

from pikaur.news import News


def run():
    with open(os.path.expanduser("~/.cache/pikaur/last_seen_news.dat"), 'w') as news_fd:
        news_fd.write("Fri, 03 May 2018 20:27:33 +0000")

    intercepted: InterceptSysOutput
    with InterceptSysOutput() as _intercepted:
        news = News()
        news.fetch_latest()
        news.print_news()
        intercepted = _intercepted

    assert len(intercepted.stdout_text.splitlines()) > 4
