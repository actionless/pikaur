import asyncio
import ssl
import email
import json
from urllib.parse import urlencode


class NetworkTaskResult():
    return_code = None
    headers = None
    json = None


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
            "User-Agent": "pikaur/0.1",
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
    # prepare response for parsing:
    request_result, the_rest = data.split(b'\r\n', 1)
    request_result = request_result.decode()
    # parse reponse:
    parsed_response = email.message_from_bytes(the_rest)
    # from email.policy import EmailPolicy
    # parsed_response = email.message_from_bytes(headers, policy=EmailPolicy)
    headers = dict(parsed_response.items())
    # join chunked response parts into one:
    payload = ''
    if headers.get('Transfer-Encoding') == 'chunked':
        all_lines = parsed_response._payload.split('\r\n')
        while all_lines:
            length = int('0x' + all_lines.pop(0), 16)
            if length == 0:
                break
            payload += all_lines.pop(0)
    else:
        payload = parsed_response._payload

    # close the socket:
    writer.close()

    # save result:
    result = NetworkTaskResult()
    result.code = request_result.split()[1]
    result.headers = headers
    result.json = json.loads(payload)
    return result


class AurTaskWorker():

    host = 'aur.archlinux.org'
    uri = None

    def get_task(self, loop):
        return https_client_task(loop, self.host, self.uri)


class AurTaskWorker_Search(AurTaskWorker):

    def __init__(self, search_query):
        params = urlencode({
            'v': 5,
            'type': 'search',
            'arg': search_query,
            'by': 'name-desc'
        })
        self.uri = f'/rpc/?{params}'


class AurTaskWorker_Info(AurTaskWorker):

    def __init__(self, packages):
        params = urlencode({
            'v': 5,
            'type': 'info',
        })
        for package in packages:
            params += '&arg[]=' + package
        self.uri = f'/rpc/?{params}'
