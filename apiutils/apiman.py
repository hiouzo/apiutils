import collections
import json
import os
import re
import uuid
from pathlib import Path
from urllib.parse import parse_qs

import click
import genson
import jsonschema
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

        self.response_line, self.raw_headers, self.body = util.http_split_message(payload)
        self.headers = util.http_parse_headers(self.raw_headers)
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


class Postman(dict):
    class Folder(dict):
        def __init__(self, name):
            super().__init__({
                'name': name,
                'item': []
            })

        @property
        def actions(self):
            return self['item']

    class Action(dict):
        def __init__(self, name):
            super().__init__({
                'name': name,
                'request': None,
                'response': []
            })

        @property
        def request(self):
            return self['request']

        @request.setter
        def request(self, request):
            self['request'] = request

        @property
        def responses(self):
            return self['response']

    class Headers(list):
        def __init__(self, headers):
            super().__init__()
            for key, value in sorted(headers.items()):
                self.append({
                    'key': key.title(),
                    'value': value,
                })

    class Request(dict):
        def __init__(self, url, method, headers, body):
            super().__init__({
                'url': url,
                'method': method,
                'headers': Postman.Headers(headers),
            })

            if not body:
                return

            self.update({
                'body': {
                    'mode': 'raw',
                    'raw': body,
                }
            })

    class Response(dict):
        # noinspection PyPep8Naming
        def __init__(self, name, originalRequest, code, status, headers, responseTime, body):
            super().__init__({
                'id': str(uuid.uuid4()),
                'name': name,
                'originalRequest': originalRequest,
                'code': code,
                'status': status,
                'headers': Postman.Headers(headers),
                'responseTime': responseTime,
                'body': body,
            })

    def __init__(self, name):
        super().__init__({
            'info': {
                'name': name,
                'description': '由 apiman 自动产生。',
                'schema': 'https://schema.getpostman.com/json/collection/v2.0.0/collection.json'
            },
            'item': []
        })

    @property
    def folders(self):
        return self['item']


class ApiMan(object):
    def __init__(self, title, host, keep_list_item, data_dir, output_file):
        self.title = title
        self.host = host.rstrip('/')
        self.keep_list_item = keep_list_item
        self.data_dir = data_dir
        self.output_file = output_file

        self.postman = Postman(title)

    def run(self):
        for root, _, files in os.walk(self.data_dir):
            apifiles = [fn for fn in files if fn.endswith('.api')]
            if not apifiles:
                continue
            # noinspection PyTypeChecker
            folder = self.process_folder(root, apifiles)
            self.postman.folders.append(folder)

        self.validate()
        self.output()

    def validate(self):
        """校验 Schema

        参考： http://sacharya.com/validating-json-using-python-jsonschema/
        """
        schema_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'postman/schema.json'
        )
        schema = json.load(open(schema_file))
        try:
            jsonschema.validate(self.postman, schema)
        except jsonschema.SchemaError as e:
            print(e)
        except jsonschema.ValidationError as e:
            print(e.message)

    def output(self):
        with open(self.output_file, 'w') as fp:
            json.dump(
                self.postman,
                fp,
                ensure_ascii=False,
                sort_keys=True,
                indent=2
            )

    def process_folder(self, root, apifiles):
        folder = Postman.Folder(root.lstrip('./'))

        actions = collections.OrderedDict()

        # 按名称分组
        for filename in apifiles:
            name = re.sub(r'^[\d_]+-(.*?)\.api', r'\1', filename)
            actions.setdefault(name, []).append(filename)

        for name, filenames in actions.items():
            action = self.process_action(root, name, filenames)
            folder.actions.append(action)

        return folder

    def process_action(self, root, apiname, filenames):
        api = Api()
        for filename in filenames:
            api.add_session(self.read_session(Path(root) / filename))

        action = Postman.Action('%s [%s]' % (apiname, api.path))

        for seq_no, session in enumerate(api.sessions, 1):
            request = self.create_request(session.request)
            if seq_no == 1:
                action.request = request
            response = self.create_response(seq_no, request, session.response)
            action.responses.append(response)

        return action

    def create_request(self, req):
        url = '%s%s' % (self.host, req.url)
        return Postman.Request(url, req.method, req.headers, req.simplified_body)

    # noinspection PyPep8Naming,PyMethodMayBeStatic
    def create_response(self, seq_no, originalRequest, resp):
        name = '#%d-%s' % (seq_no, resp.status_code)

        return Postman.Response(
            name,
            originalRequest,
            int(resp.status_code),
            resp.reason,
            resp.headers,
            int(float(resp.latency) * 1000),
            resp.simplified_body,
        )

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
@click.option('--title', '-t', default=None, help='API 标题.')
@click.option('--host', '-h', default='http://{host}', help='API 主机.')
@click.option('--keep-list-item', '-k', default=3, help='列表中保留的项数.')
@click.option('--data-dir', '-d', default='.', help='API 数据文件目录.')
@click.option('--output', '-o', help='Postman 文件名.')
def run(title, host, keep_list_item, data_dir, output):
    if not output:
        if title is not None:
            output = 'apiman-%s.json' % (re.sub('[^\w.]', '-', title).lower())
        else:
            output = 'apiman.json'
    if title is None:
        title = 'API - Apiman'
    apiblue = ApiMan(title, host, keep_list_item, data_dir, output)
    apiblue.run()


if __name__ == "__main__":
    run()
