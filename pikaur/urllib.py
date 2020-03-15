import gzip
import json
from urllib import request
from urllib.error import URLError
from typing import Any, Dict

from .i18n import _
from .pprint import print_error, print_stderr, color_line
from .prompt import ask_to_continue
from .exceptions import SysExit
from .args import parse_args


def read_bytes_from_url(url: str, optional=False) -> bytes:
    if parse_args().print_commands:
        print_stderr(
            color_line('=> ', 14) + f'GET {url}'
        )
    req = request.Request(url)
    try:
        response = request.urlopen(req)
    except URLError as exc:
        print_error('urllib: ' + str(exc.reason))
        if optional:
            return b''
        if ask_to_continue(_('Do you want to retry?')):
            return read_bytes_from_url(url, optional=optional)
        raise SysExit(102)
    result_bytes = response.read()
    return result_bytes


def get_unicode_from_url(url: str, optional=False) -> str:
    result_bytes = read_bytes_from_url(url, optional=optional)
    return result_bytes.decode('utf-8')


def get_json_from_url(url: str) -> Dict[str, Any]:
    result_json = json.loads(get_unicode_from_url(url))
    return result_json


def get_gzip_from_url(url: str) -> str:
    result_bytes = read_bytes_from_url(url)
    decompressed_bytes_response = gzip.decompress(result_bytes)
    text_response = decompressed_bytes_response.decode('utf-8')
    return text_response
