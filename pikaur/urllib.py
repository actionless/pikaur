import gzip
import json
import socket
from urllib import request
from urllib.error import URLError
from typing import Any, Dict, List

from .i18n import _
from .pprint import print_error, print_stderr, color_line
from .prompt import ask_to_continue
from .exceptions import SysExit
from .args import parse_args
from .config import PikaurConfig


def read_bytes_from_url(url: str, optional=False) -> bytes:
    if parse_args().print_commands:
        print_stderr(
            color_line('=> ', 14) + f'GET {url}'
        )
    req = request.Request(url)
    try:
        response = request.urlopen(req)
    except URLError as exc:
        print_error(f'GET {url}')
        print_error('urllib: ' + str(exc.reason))
        if optional:
            return b''
        if ask_to_continue(_('Do you want to retry?')):
            return read_bytes_from_url(url, optional=optional)
        raise SysExit(102) from exc
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
    try:
        decompressed_bytes_response = gzip.decompress(result_bytes)
    except EOFError as exc:
        print_error(f'GET {url}')
        print_error('urllib: ' + str(exc))
        if ask_to_continue(_('Do you want to retry?')):
            return get_gzip_from_url(url)
        raise SysExit(102) from exc
    text_response = decompressed_bytes_response.decode('utf-8')
    return text_response


class ProxyInitSocks5Error(Exception):
    pass


def init_proxy() -> None:
    net_config = PikaurConfig().network

    socks_proxy_addr = net_config.Socks5Proxy.get_str()
    if socks_proxy_addr:  # pragma: no cover
        port = 1080
        idx = socks_proxy_addr.find(':')
        if idx >= 0:
            port = int(socks_proxy_addr[idx + 1:])
            socks_proxy_addr = socks_proxy_addr[:idx]

        try:
            import socks  # type: ignore[import] #  pylint:disable=import-outside-toplevel
        except ImportError as exc:
            raise ProxyInitSocks5Error(
                _("pikaur requires python-pysocks to use a socks5 proxy.")
            ) from exc
        socks.set_default_proxy(socks.PROXY_TYPE_SOCKS5, socks_proxy_addr, port)
        socket.socket = socks.socksocket  # type: ignore[misc]

    http_proxy_addr = net_config.AurHttpProxy.get_str()
    https_proxy_addr = net_config.AurHttpsProxy.get_str()
    if http_proxy_addr or https_proxy_addr:
        proxies = {}
        if http_proxy_addr:
            proxies['http'] = http_proxy_addr
        if https_proxy_addr:
            proxies['https'] = https_proxy_addr
        proxy_support = request.ProxyHandler(proxies)
        opener = request.build_opener(proxy_support)
        request.install_opener(opener)


def wrap_proxy_env(cmd: List[str]) -> List[str]:
    """
    add env with proxy to command line args
    """
    net_config = PikaurConfig().network
    http_proxy_addr = net_config.AurHttpProxy.get_str()
    https_proxy_addr = net_config.AurHttpsProxy.get_str()
    if not (http_proxy_addr or https_proxy_addr):
        return cmd
    proxy_prefix = ['env', ]
    if http_proxy_addr:
        proxy_prefix.append(f'HTTP_PROXY={http_proxy_addr}')
    if https_proxy_addr:
        proxy_prefix.append(f'HTTPS_PROXY={https_proxy_addr}')
    return proxy_prefix + cmd
