import asyncio
import ssl
import email
import json
from urllib.parse import urlencode


async def https_client(loop, host, uri, result_container=None, port=443):
    result_container = result_container or {}
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
    result, the_rest = data.split(b'\r\n', 1)
    result = result.decode()
    # parse reponse:
    parsed_response = email.message_from_bytes(the_rest)
    # from email.policy import EmailPolicy
    # parsed_response = email.message_from_bytes(headers, policy=EmailPolicy)
    headers = dict(parsed_response.items())
    # join chunked response parts into one:
    payload = ''
    if headers.get('Transfer-Encoding') == 'chunked':
        all_lines = parsed_response._payload.split('\r\n')
        while True:
            length = int('0x' + all_lines.pop(0), 16)
            payload += all_lines.pop(0)
            if length == 0:
                break
    else:
        payload = parsed_response._payload

    # write result:
    result_container['code'] = result.split()[1]
    result_container['headers'] = headers
    result_container['json'] = json.loads(payload)

    # close the socket:
    writer.close()
    return result_container


def search_packages(loop, search_query):
    host = 'aur.archlinux.org'
    params = urlencode({
        'v': 5,
        'type': 'search',
        'arg': search_query,
        'by': 'name-desc'
    })
    uri = f'/rpc/?{params}'
    return https_client(loop, host, uri)


if __name__ == '__main__':
    host = 'aur.archlinux.org'
    params = urlencode({
        'v': 5,
        'type': 'search',
        'arg': 'oomox',
        # 'arg': 'oomox-git',
        # 'arg': 'linux',
        'by': 'name-desc'
    })
    uri = f'/rpc/?{params}'

    # host = 'transfer.sh'
    # uri = '/Namit/test.txt'

    loop = asyncio.get_event_loop()
    result = {}
    loop.run_until_complete(
        https_client(loop, host, uri, result_container=result)
    )
    loop.close()

    # from pprint import pprint
    # print('=' * 30)
    # pprint(result)
    print(
        [r['Name'] for r in result['json']['results']]
    )
