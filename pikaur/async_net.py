import asyncio
import ssl
import email
import json
import gzip
from typing import List, Dict, Any, Type
from abc import ABCMeta, abstractmethod

from .config import VERSION
from .pprint import print_status_message
from .core import DataType


class NetworkTaskResult(DataType, metaclass=ABCMeta):
    return_code: int = None
    headers: Dict[str, str] = None

    @classmethod
    @abstractmethod
    def from_bytes(cls, bytes_response: bytes) -> 'NetworkTaskResult':
        pass


class NetworkTaskResultJSON(NetworkTaskResult):
    json: Dict[str, Any] = None

    @classmethod
    def from_bytes(cls, bytes_response: bytes) -> 'NetworkTaskResultJSON':
        # prepare response for parsing:
        string_response = bytes_response.decode('utf-8')
        request_result, the_rest = string_response.split('\r\n', 1)
        # parse reponse:
        parsed_response = email.message_from_string(the_rest)
        # from email.policy import EmailPolicy
        # parsed_response = email.message_from_string(
        #    headers, policy=EmailPolicy
        # )
        headers = {k: str(v) for k, v in parsed_response.items()}
        # join chunked response parts into one:
        string_payload = ''
        parsed_payload = parsed_response.get_payload()
        if not isinstance(parsed_payload, str):
            raise RuntimeError()
        if headers.get('Transfer-Encoding') == 'chunked':
            all_lines = parsed_payload.split('\r\n')
            while all_lines:
                length = int('0x' + all_lines.pop(0), 16)
                if length == 0:
                    break
                string_payload += all_lines.pop(0)
        else:
            string_payload = parsed_payload

        # save result:
        self = cls()
        self.return_code = int(request_result.split()[1])
        self.headers = headers
        try:
            self.json = json.loads(string_payload)
        except Exception as exc:
            print_status_message(f'PAYLOAD: {string_payload}')
            raise exc
        return self


class NetworkTaskResultGzip(NetworkTaskResult):
    text: str = None

    @staticmethod
    def parse_headers(all_lines: List[bytes]) -> Dict[str, str]:
        headers = {}
        ready_to_parse = False
        while all_lines:
            line = all_lines[0]
            if not ready_to_parse:
                all_lines.remove(line)
                if line == b'':
                    ready_to_parse = True
                    continue
                elif b':' in line:
                    header, *the_rest = line.split(b':')
                    value = b':'.join(the_rest).strip()
                    headers[header.decode('utf-8')] = value.decode('utf-8')
            if ready_to_parse:
                break
        return headers

    @staticmethod
    def parse_chunked_response(all_lines: List[bytes]) -> bytes:
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
        return response_payload

    @classmethod
    def from_bytes(cls, bytes_response: bytes) -> 'NetworkTaskResultGzip':
        all_lines = bytes_response.split(b'\r\n')
        return_code = int(all_lines[0].split()[1])
        headers = cls.parse_headers(all_lines)
        response_payload = cls.parse_chunked_response(all_lines)
        # decode and save the result:
        decompressed_bytes_response = gzip.decompress(response_payload)
        text_response = decompressed_bytes_response.decode('utf-8')
        return cls(
            return_code=return_code,
            headers=headers,
            text=text_response
        )


async def https_client_task(
        loop: asyncio.AbstractEventLoop,
        host: str,
        uri: str,
        result_class: Type[NetworkTaskResult],
        content_type="application/json",
) -> NetworkTaskResult:

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
