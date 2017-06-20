import gzip
import json
import socket
import time

import binascii


def http_split_message(data):
    first_line, _, data = data.partition(b'\r\n')
    raw_headers, _, body = data.partition(b'\r\n\r\n')

    # ! Header 中有时会有非 utf-8 编码
    return first_line.decode(errors='replace'), raw_headers.decode('iso-8859-1'), body


def http_parse_headers(raw_headers):
    headers = {}
    key = value = None
    for line in raw_headers.splitlines(False):
        if not line:
            continue
        if line[0] not in " \t":
            key, _, value = line.partition(":")
            key = key.strip().lower()
            headers[key] = value.strip()
        else:
            headers[key] += value.strip()

    return headers


# noinspection PyShadowingBuiltins
def strftime(timestamp, format='%Y-%m-%d %H:%M:%S'):
    return time.strftime(format, time.localtime(timestamp))


def simplify(data, keep_list_item=3):
    # ! 不能用 map, 因为 map 不会立即执行
    if isinstance(data, dict):
        for value in data.values():
            simplify(value, keep_list_item)
    elif isinstance(data, list):
        del data[keep_list_item:]
        for item in data:
            simplify(item, keep_list_item)


def decode_body(headers, body):
    body = body

    # Transfer-Encoding: chunked
    if headers.get("transfer-encoding") == "chunked":
        chunks = []
        while body:
            length, _, body = body.partition(b"\r\n")
            length = int(length, 0x10)
            if length == 0:
                break
            chunks.append(body[:length])
            body = body[length + 2:]
        body = b"".join(chunks)

    # Content-Encoding: gzip
    if headers.get("content-encoding") == "gzip":
        try:
            body = gzip.decompress(body)
        except OSError:
            pass

    try:
        body = body.decode("utf-8")
    except UnicodeDecodeError:
        body = body.decode("utf-8", "replace")

    return body


def simplify_body(body, keep_list_item):
    # noinspection PyBroadException
    try:
        obj = json.loads(body)
    except:
        return body

    # 简化数据，只保留部分数据
    simplify(obj, keep_list_item)
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)


def hack_gor_real_ip(headers):
    if not headers.startswith('X-Real-IP:'):
        return headers

    line, _, other = headers.partition('\r\n')
    real_ip = line.strip().partition(':')[2].strip()
    if real_ip.endswith('::'):
        # noinspection PyBroadException
        try:
            _12, _34, _ = real_ip.strip().split(":", 2)
            real_ip = binascii.unhexlify(_12.rjust(4, "0") + _34.rjust(4, "0"))
            real_ip = socket.inet_ntoa(real_ip)
        except:
            return headers
        else:
            line = 'X-Real-IP: %s' % real_ip
            return '\r\n'.join((line, other))
    else:
        return headers


def guess_value_type(value):
    '''猜一猜数据类型
    '''
    try:
        int(value)
    except ValueError:
        pass
    else:
        return 'integer'

    try:
        float(value)
    except ValueError:
        pass
    else:
        return 'number'

    if isinstance(value, str):
        if value.lower() in ('true', 'false'):
            return 'boolean'
        return 'string'

    return 'string'
