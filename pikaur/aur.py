import asyncio
import ssl
import email
import json
from urllib.parse import urlencode, quote

from .core import MultipleTasksExecutor, DataType, get_chunks
from .config import VERSION


class NetworkTaskResult():
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
            print(f'PAYLOAD: {payload}')
            raise exc
        return self


async def https_client_task(loop, host, uri, port=443):
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
            "Content-type": "application/json",
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
    return NetworkTaskResult.from_bytes(data)


class AURPackageInfo(DataType):
    Name = None
    Version = None
    Description = None
    NumVotes = None
    Popularity = None
    Depends = None
    MakeDepends = None
    Conflicts = None
    Replaces = None

    ID = None  # pylint: disable=invalid-name
    PackageBaseID = None
    PackageBase = None
    URL = None
    OutOfDate = None
    Maintainer = None
    FirstSubmitted = None
    LastModified = None
    URLPath = None
    OptDepends = None
    Provides = None
    License = None
    Keywords = None
    Groups = None
    CheckDepends = None


class AurTaskWorker():

    host = 'aur.archlinux.org'
    uri = None
    params = None

    async def aur_client_task(self, loop):
        raw_result = await https_client_task(
            loop, self.host, self.uri, port=443
        )
        return [
            AURPackageInfo(**aur_json)
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


def find_aur_packages(package_names):
    # @TODO: return only packages for the current architecture
    package_names = list(package_names)[:]
    json_results = []
    for package_name in package_names[:]:
        aur_pkg = _AUR_PKGS_FIND_CACHE.get(package_name)
        if aur_pkg:
            json_results.append(aur_pkg)
            package_names.remove(package_name)

    if package_names:
        results = MultipleTasksExecutor({
            _id: AurTaskWorkerInfo(packages=packages_chunk)
            for _id, packages_chunk in enumerate(
                get_chunks(package_names, chunk_size=100)
            )
        }).execute()

        for result in results.values():
            for aur_pkg in result:
                _AUR_PKGS_FIND_CACHE[aur_pkg.Name] = aur_pkg
                json_results.append(aur_pkg)

    found_aur_packages = [
        result.Name for result in json_results
    ]
    not_found_packages = []
    if len(package_names) != len(found_aur_packages):
        not_found_packages = [
            package for package in package_names
            if package not in found_aur_packages
        ]

    return json_results, not_found_packages


def get_repo_url(package_name):
    package_base_name = find_aur_packages([package_name])[0][0].PackageBase
    return f'https://aur.archlinux.org/{package_base_name}.git'
