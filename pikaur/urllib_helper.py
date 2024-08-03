import gzip
import json
import socket
from time import sleep
from typing import TYPE_CHECKING
from urllib import request
from urllib.error import URLError

from .args import parse_args
from .config import PikaurConfig
from .exceptions import SysExit
from .i18n import translate
from .pikaprint import ColorsHighlight, color_line, print_error, print_stderr
from .prompt import ask_to_continue

if TYPE_CHECKING:
    from typing import Any, Final


DEFAULT_WEB_ENCODING: "Final" = "utf-8"
NOCONFIRM_RETRY_INTERVAL: "Final" = 3


def read_bytes_from_url(
        url: str,
        *,
        optional: bool = False,
        autoretry: bool = True,
) -> bytes:
    args = parse_args()
    if args.print_commands:
        print_stderr(
            color_line("=> ", ColorsHighlight.cyan) + f"GET {url}",
        )
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
    try:
        with request.urlopen(req) as response:  # nosec B310  # noqa: S310
            result_bytes: bytes = response.read()
            return result_bytes
    except URLError as exc:
        print_error(f"GET {url}")
        print_error("urllib: " + str(exc.reason))
        if autoretry and ask_to_continue(translate("Do you want to retry?")):  # pragma: no cover
            if args.noconfirm:
                print_stderr(
                    translate("Sleeping for {} seconds...").format(
                        NOCONFIRM_RETRY_INTERVAL,
                    ),
                )
                sleep(NOCONFIRM_RETRY_INTERVAL)
            return read_bytes_from_url(url, optional=optional)
        if optional:
            return b""
        raise SysExit(102) from exc


def get_unicode_from_url(url: str, *, optional: bool = False) -> str:
    result_bytes = read_bytes_from_url(url, optional=optional)
    return result_bytes.decode(DEFAULT_WEB_ENCODING)


def get_json_from_url(url: str) -> "Any":
    return json.loads(get_unicode_from_url(url))


def get_gzip_from_url(url: str, *, autoretry: bool = True) -> str:
    result_bytes = read_bytes_from_url(url)
    try:
        decompressed_bytes_response = gzip.decompress(result_bytes)
    except Exception as exc:
        print_error(f"GET {url}")
        print_error("urllib: " + str(exc))
        if autoretry and ask_to_continue(translate("Do you want to retry?")):  # pragma: no cover
            args = parse_args()
            if args.noconfirm:
                print_stderr(
                    translate("Sleeping for {} seconds...").format(
                        NOCONFIRM_RETRY_INTERVAL,
                    ),
                )
                sleep(NOCONFIRM_RETRY_INTERVAL)
            return get_gzip_from_url(url)
        raise SysExit(102) from exc
    return decompressed_bytes_response.decode(DEFAULT_WEB_ENCODING)


class ProxyInitSocks5Error(Exception):
    pass


def init_proxy() -> None:
    net_config = PikaurConfig().network

    socks_proxy_addr = net_config.Socks5Proxy.get_str()
    if socks_proxy_addr:  # pragma: no cover
        port = 1080
        idx = socks_proxy_addr.find(":")
        if idx >= 0:
            port = int(socks_proxy_addr[idx + 1:])
            socks_proxy_addr = socks_proxy_addr[:idx]

        try:
            import socks  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel  # noqa: PLC0415,E501,RUF100
        except ImportError as exc:
            raise ProxyInitSocks5Error(
                translate("pikaur requires python-pysocks to use a socks5 proxy."),
            ) from exc
        socks.set_default_proxy(socks.PROXY_TYPE_SOCKS5, socks_proxy_addr, port)
        socket.socket = socks.socksocket  # type: ignore[misc]

    http_proxy_addr = net_config.AurHttpProxy.get_str()
    https_proxy_addr = net_config.AurHttpsProxy.get_str()
    if http_proxy_addr or https_proxy_addr:  # pragma: no cover
        proxies = {}
        if http_proxy_addr:
            proxies["http"] = http_proxy_addr
        if https_proxy_addr:
            proxies["https"] = https_proxy_addr
        proxy_support = request.ProxyHandler(proxies)
        opener = request.build_opener(proxy_support)
        request.install_opener(opener)


def wrap_proxy_env(cmd: list[str]) -> list[str]:  # pragma: no cover:
    """Add env with proxy to command line args."""
    net_config = PikaurConfig().network
    http_proxy_addr = net_config.AurHttpProxy.get_str()
    https_proxy_addr = net_config.AurHttpsProxy.get_str()
    if not (http_proxy_addr or https_proxy_addr):
        return cmd
    proxy_prefix = ["env"]
    if http_proxy_addr:
        proxy_prefix.append(f"HTTP_PROXY={http_proxy_addr}")
    if https_proxy_addr:
        proxy_prefix.append(f"HTTPS_PROXY={https_proxy_addr}")
    return proxy_prefix + cmd
