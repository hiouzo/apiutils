import collections
import json
import os
import re
import textwrap
from pathlib import Path
from urllib.parse import parse_qs

import click
import genson
from apiutils import util


class HTTPMessage(object):
    headers = dict()
    body = b''
    decoded_body = ''
    simplified_body = ''
    schema = None

    def parse_body(self, keep_list_item):
        self.decoded_body = util.decode_body(self.headers, self.body)

        # noinspection PyBroadException
        try:
            obj = json.loads(self.decoded_body)
        except:
            self.simplified_body = self.decoded_body
            return

        # 简化数据，只保留部分数据
        util.simplify(obj, keep_list_item)
        self.simplified_body = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)

        # 保存数据 Schema 以供比较
        self.schema = genson.Schema()
        self.schema.add_object(obj)

    def compare_body(self, other):
        if self.schema and other.schema:
            return self.schema.to_json(sort_keys=True) == other.schema.to_json(sort_keys=True)
        return self.simplified_body == other.simplified_body


class Request(HTTPMessage):
    def __init__(self, timestamp, payload):
        self.timestamp = timestamp
        self.payload = payload

        self.request_line, raw_headers, self.body = util.http_split_message(payload)
        self.raw_headers = util.hack_gor_real_ip(raw_headers)
        self.headers = util.http_parse_headers(self.raw_headers)
        self.method, self.url, self.version = self.request_line.split(' ')

        self.host = self.headers.get('host', 'n/a')
        self.path, _, self.query = self.url.partition('?')

    def __str__(self):
        return '%s %s' % (self.timestamp, self.request_line)

    def like(self, other):
        return self.method == other.method and self.compare_body(other)


class Response(HTTPMessage):
    def __init__(self, latency, payload):
        self.latency = latency
        self.payload = payload

        self.response_line, raw_headers, self.body = util.http_split_message(payload)
        self.headers = util.http_parse_headers(raw_headers)
        self.version, self.status_code, self.reason = self.response_line.split(' ', 2)

    def __str__(self):
        return '%s %s' % (self.latency, self.response_line)

    def like(self, other):
        return self.response_line == other.response_line and self.compare_body(other)

    def compare_body(self, other):
        if self.schema and other.schema:
            # !!! 这里已经深入 API 数据内部，不再是通用的代码
            # 如果 Response 中的 code 不同则认为不同
            data = json.loads(self.simplified_body)
            if isinstance(data, dict) and 'code' in data:
                other_data = json.loads(other.simplified_body)
                if isinstance(other_data, dict) and 'code' in other_data:
                    if data['code'] != other_data['code']:
                        return False

        return super().compare_body(other)


class ApiSession(object):
    """Session = Request + Response
    """
    def __init__(self, request, response):
        self.request = request
        self.response = response

        self.method = request.method

        self.parameters = parse_qs(request.query)

    def like(self, other):
        return self.request.like(other.request) and self.response.like(other.response)


class Api:
    """
    """
    path = None

    def __init__(self):
        self.sessions = []
        self.parameters = collections.OrderedDict()

    def add_session(self, session):
        # 检查是不是和原来的 session 重复
        for s in self.sessions:
            if s.like(session):
                return

        self.sessions.append(session)
        if self.path is None:
            self.path = session.request.path
        self.parameters.update(session.parameters)

    @property
    def url_template(self):
        """符合 API Blueprint 的 URL
        """
        if self.parameters:
            names = ','.join(self.parameters.keys())
            return '%s{?%s}' % (self.path, names)
        else:
            return self.path


class ApiBlue(object):
    def __init__(self, title, host, keep_list_item, data_dir, output):
        self.title = title
        self.host = host
        self.keep_list_item = keep_list_item
        self.data_dir = data_dir
        self.output = output

    def write(self, data):
        if isinstance(data, bytes):
            self.output.write(data)
        else:
            self.output.write(data.encode())

    def run(self):
        self.write_header()

        for root, _, files in os.walk(self.data_dir):
            apifiles = [fn for fn in files if fn.endswith('.api')]
            if not apifiles:
                continue
            # noinspection PyTypeChecker
            self.write_group(Path(root), apifiles)

    def write_header(self):
        self.write('FORMAT: 1A\n')
        self.write('HOST: %s\n\n' % self.host)
        self.write('# %s\n\n' % self.title)

    def write_group(self, root, apifiles):
        self.write('# Group %s\n\n' % root)
        apis = collections.OrderedDict()

        # 按名称分组
        for filename in apifiles:
            name = re.sub(r'^[\d_]+-(.*?)\.api', r'\1', filename)
            apis.setdefault(name, []).append(filename)

        for name, filenames in apis.items():
            self.write_api(root, name, filenames)

    def write_api(self, root, apiname, filenames):
        api = Api()
        for filename in filenames:
            api.add_session(self.read_session(root / filename))

        self.write('## %s [%s]\n\n' % (apiname, api.path))
        last_method = None
        for seq_no, session in enumerate(api.sessions, 1):
            if last_method != session.method:
                self.write('### %s %s [%s %s]\n\n' % (
                    session.method, apiname, session.method, api.url_template))
                self.write_parameters(api.parameters)
                last_method = session.method
            if len(api.sessions) > 1:
                self.write_session(session, seq_no)
            else:
                self.write_session(session)

    def write_session(self, session, seq_no=None):
        self.write_request(session.request, seq_no)
        self.write_response(session.response)

    def write_parameters(self, parameters):
        if not parameters:
            return
        self.write('+ Parameters\n')
        for name, value in parameters.items():
            if len(value) == 1:
                value = value[0]
            self.write('    + `%s`: `%s` (string)\n' % (name, value))
        self.write('\n')

    def write_request(self, request, seq_no=None):
        if not request.body and not seq_no:
            return
        content_type = request.headers.get('content-type', 'N/A')
        if seq_no:
            self.write('+ Request #%d (%s)\n\n' % (seq_no, content_type))
        else:
            self.write('+ Request (%s)\n\n' % content_type)
        self.write('    ```\n')
        self.write('    %s %s%s\n' % (request.method, self.host.rstrip('/'), request.url))
        self.write('    ```\n\n')
        self.write_body(request.simplified_body)
        self.write('\n\n')

    def write_response(self, response):
        content_type = response.headers.get('content-type', 'N/A')
        self.write('+ Response %s (%s)\n\n' % (response.status_code, content_type))
        self.write_body(response.simplified_body)
        self.write('\n\n')

    def write_body(self, body):
        if not body:
            body = '<empty>'
        self.write('    + Body\n\n')
        self.write(textwrap.indent(body, '            '))

    def read_session(self, apifile):
        fp = apifile.open('rb')

        # API Headers
        headers = self.read_headers(fp)
        timestamp = headers.get('request-time', 'N/A')
        latency = headers.get('latency', 'N/A')

        # Request
        line = fp.readline()
        if not line.startswith(b'Request '):
            print('API 文件格式错误(1):', fp.name)
            return
        length = int(line.partition(b' ')[-1])
        payload = fp.read(length)

        request = Request(timestamp, payload)
        request.parse_body(self.keep_list_item)

        # Skip empty line
        line = fp.readline()
        if line != b'\r\n':
            print('API 文件格式错误(2):', fp.name)
            return

        # Response
        line = fp.readline()
        if not line.startswith(b'Response '):
            print('API 文件格式错误(3):', fp.name)
            return
        length = int(line.partition(b' ')[-1])
        payload = fp.read(length)

        response = Response(latency, payload)
        response.parse_body(self.keep_list_item)

        return ApiSession(request, response)

    @staticmethod
    def read_headers(fp):
        headers = {}
        for line in fp:
            if line == b'\r\n':
                break
            name, _, value = line.decode().partition(':')
            headers[name.lower()] = value.strip()
        return headers


@click.command()
@click.option('--title', '-t', default='API', help='API 标题.')
@click.option('--host', '-h', default='http://{host}', help='API 主机.')
@click.option('--keep-list-item', '-k', default=3, help='列表中保留的项数.')
@click.option('--data-dir', '-d', default='.', help='API 数据文件目录.')
@click.option('--output', '-o', default='api.apib', type=click.File('wb'), help='API Blueprint 文件名.')
def run(title, host, keep_list_item, data_dir, output):
    apiblue = ApiBlue(title, host, keep_list_item, data_dir, output)
    apiblue.run()


if __name__ == "__main__":
    run()
