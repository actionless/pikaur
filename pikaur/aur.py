import asyncio
import ssl
import email
import json
import gzip
from urllib.parse import urlencode, quote

from .core import (
    DataType, get_chunks,
    SingleTaskExecutor, MultipleTasksExecutorPool
)
from .config import VERSION
from .i18n import _
from .pprint import print_status_message


class NetworkTaskResultJson():
    return_code = None
    headers = None
    json = None

    @classmethod
    def from_bytes(cls, bytes_response):
        # prepare response for parsing:
        bytes_response = bytes_response.decode('utf-8')
        request_result, the_rest = bytes_response.split('\r\n', 1)
        # parse reponse:
        parsed_response = email.message_from_string(the_rest)
        # from email.policy import EmailPolicy
        # parsed_response = email.message_from_string(
        #    headers, policy=EmailPolicy
        # )
        headers = dict(parsed_response.items())
        # join chunked response parts into one:
        payload = ''
        if headers.get('Transfer-Encoding') == 'chunked':
            all_lines = parsed_response.get_payload().split('\r\n')
            while all_lines:
                length = int('0x' + all_lines.pop(0), 16)
                if length == 0:
                    break
                payload += all_lines.pop(0)
        else:
            payload = parsed_response.get_payload()

        # save result:
        self = cls()
        self.return_code = request_result.split()[1]
        self.headers = headers
        try:
            self.json = json.loads(payload)
        except Exception as exc:
            print_status_message(f'PAYLOAD: {payload}')
            raise exc
        return self


class NetworkTaskResultGzip(DataType):
    return_code = None
    headers = None
    text = None

    @classmethod
    def from_bytes(cls, bytes_response):
        # parse headers:
        ready_to_parse = False
        all_lines = bytes_response.split(b'\r\n')
        return_code = all_lines[0].split()[1]
        headers = {}
        while all_lines:
            line = all_lines[0]
            if not ready_to_parse:
                all_lines.remove(line)
                if line == b'':
                    ready_to_parse = True
                    continue
                elif b':' in line:
                    header, *value = line.split(b':')
                    value = b':'.join(value).strip()
                    headers[header] = value
            if ready_to_parse:
                break

        # cut chunked response tail:
        ready_to_parse = False
        while all_lines:
            line = all_lines[len(all_lines)-1]
            if line == b'0':
                ready_to_parse = True
            if ready_to_parse:
                break
            else:
                all_lines.remove(line)

        # join chunked response parts into one:
        chunk_size = int(all_lines[0], 16)
        remained_to_parse = b'\r\n'.join(all_lines[1:])
        response_payload = b''
        while remained_to_parse:
            response_payload += remained_to_parse[:chunk_size]
            remained_to_parse = remained_to_parse[chunk_size+1:]
            all_lines = remained_to_parse.split(b'\r\n')
            chunk_size = int(all_lines[0], 16)
            remained_to_parse = b'\r\n'.join(all_lines[1:])

        # decode and save the result:
        decompressed_bytes_response = gzip.decompress(response_payload)
        text_response = decompressed_bytes_response.decode('utf-8')
        return cls(
            return_code=return_code,
            headers=headers,
            text=text_response
        )


async def https_client_task(
        loop, host, uri,
        content_type="application/json",
        result_class=NetworkTaskResultJson
):
    port = 443
    # open SSL connection:
    ssl_context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
    )
    reader, writer = await asyncio.open_connection(
        host, port,
        ssl=ssl_context, loop=loop
    )

    # prepare request data:
    action = f'GET {uri} HTTP/1.1\r\n'
    headers = '\r\n'.join([
        f'{key}: {value}' for key, value in {
            "Host": host,
            "Content-type": content_type,
            "User-Agent": f"pikaur/{VERSION}",
            "Accept": "*/*"
        }.items()
    ]) + '\r\n'
    body = '\r\n' + '\r\n'
    request = f'{action}{headers}{body}\x00'
    # send request:
    writer.write(request.encode())
    await writer.drain()

    # read response:
    data = await reader.read()
    # close the socket:
    writer.close()
    return result_class.from_bytes(data)


class AURPackageInfo(DataType):
    name = None
    version = None
    desc = None
    numvotes = None
    popularity = None
    depends = None
    makedepends = None
    conflicts = None
    replaces = None

    id = None  # pylint: disable=invalid-name
    packagebaseid = None
    packagebase = None
    url = None
    outofdate = None
    maintainer = None
    firstsubmitted = None
    lastmodified = None
    urlpath = None
    optdepends = None
    provides = None
    license = None
    keywords = None
    groups = None
    checkdepends = None

    def __init__(self, **kwargs):
        if 'description' in kwargs:
            kwargs['desc'] = kwargs.pop('description')
        super().__init__(**kwargs)


class AurTaskWorker():

    host = 'aur.archlinux.org'
    uri = None
    params = None

    async def aur_client_task(self, loop):
        raw_result = await https_client_task(
            loop, self.host, self.uri,
        )
        return [
            AURPackageInfo(**{key.lower(): value for key, value in aur_json.items()})
            for aur_json in raw_result.json.get('results', [])
        ]

    def get_task(self, loop):
        self.uri = f'/rpc/?{self.params}'
        return self.aur_client_task(loop)


class AurTaskWorkerSearch(AurTaskWorker):

    def __init__(self, search_query):
        self.params = urlencode({
            'v': 5,
            'type': 'search',
            'arg': search_query,
            'by': 'name-desc'
        })


class AurTaskWorkerInfo(AurTaskWorker):

    def __init__(self, packages):
        self.params = urlencode({
            'v': 5,
            'type': 'info',
        })
        for package in packages:
            self.params += '&arg[]=' + quote(package)


_AUR_PKGS_FIND_CACHE = {}


def find_aur_packages(package_names, enable_progressbar=False):
    # @TODO: return only packages for the current architecture
    package_names = list(package_names)[:]
    json_results = []
    for package_name in package_names[:]:
        aur_pkg = _AUR_PKGS_FIND_CACHE.get(package_name)
        if aur_pkg:
            json_results.append(aur_pkg)
            package_names.remove(package_name)

    if package_names:
        results = MultipleTasksExecutorPool(
            {
                _id: AurTaskWorkerInfo(packages=packages_chunk)
                for _id, packages_chunk in enumerate(
                    # get_chunks(package_names, chunk_size=100)
                    get_chunks(package_names, chunk_size=200)
                )
            },
            pool_size=8,
            enable_progressbar=enable_progressbar
        ).execute()

        for result in results.values():
            for aur_pkg in result:
                _AUR_PKGS_FIND_CACHE[aur_pkg.name] = aur_pkg
                json_results.append(aur_pkg)

    found_aur_packages = [
        result.name for result in json_results
    ]
    not_found_packages = []
    if len(package_names) != len(found_aur_packages):
        not_found_packages = [
            package for package in package_names
            if package not in found_aur_packages
        ]

    return json_results, not_found_packages


def get_repo_url(package_name):
    package_base_name = find_aur_packages([package_name])[0][0].packagebase
    return f'https://aur.archlinux.org/{package_base_name}.git'


class AurTaskWorkerList(AurTaskWorker):

    uri = '/packages.gz'

    async def aur_client_task(self, loop):
        raw_result = await https_client_task(
            loop, self.host, self.uri, result_class=NetworkTaskResultGzip
        )
        return [
            pkg_name for pkg_name in raw_result.text.split('\n')
            if pkg_name
        ][1:]

    def get_task(self, loop):
        return self.aur_client_task(loop)


_AUR_PKGS_LIST_CACHE = None


def get_all_aur_names():
    global _AUR_PKGS_LIST_CACHE  # pylint: disable=global-statement
    if not _AUR_PKGS_LIST_CACHE:
        _AUR_PKGS_LIST_CACHE = SingleTaskExecutor(
            AurTaskWorkerList()
        ).execute()
    return _AUR_PKGS_LIST_CACHE


def get_all_aur_packages():
    return find_aur_packages(
        get_all_aur_names(),
        enable_progressbar=_("Getting ALL AUR info") + " "
    )[0]
