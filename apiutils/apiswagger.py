import collections
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs

import click
import openapi
from apiutils import util
from apiutils.apischema import build_schema
from openapi.model import Operation
from openapi.model import ParametersList
from openapi.model import PathItem
from openapi.model import QueryParameterSubSchema
from openapi.model import Responses
from openapi.model import Swagger, Info, Paths


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
        self.schema = build_schema(obj)

    def compare_body(self, other):
        if self.schema and other.schema:
            return json.dumps(self.schema, sort_keys=True) == json.dumps(other.schema, sort_keys=True)
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

        self.parameters = ParametersList()
        parameter_names = set()

        for name, value in sorted(parse_qs(request.query).items()):
            if name in parameter_names:
                continue
            parameter_names.add(name)
            if len(value) == 1:
                value = value[0]
            else:
                value = ','.join(map(str, value))
            if isinstance(value, int):
                type = 'integer'
            elif isinstance(value, float):
                type = 'number'
            else:
                type = 'string'
            self.parameters.append(QueryParameterSubSchema({
                'name': name,
                'type': type,
                'in': 'query',
                'default': value,
                'description': 'TODO: description of ' + name,
            }))

    def like(self, other):
        return self.request.like(other.request) and self.response.like(other.response)


class Api:
    """
    """
    path = None

    def __init__(self):
        self.sessions = []
        self.parameters = ParametersList()
        self.parameter_names = set()

    def add_session(self, session):
        # 检查是不是和原来的 session 重复
        for s in self.sessions:
            if s.like(session):
                return

        self.sessions.append(session)
        if self.path is None:
            self.path = session.request.path
        for parameter in session.parameters:
            if parameter['name'] in self.parameter_names:
                continue
            self.parameter_names.add(parameter['name'])
            self.parameters.append(parameter)


class ApiSwagger(object):
    def __init__(self, title, host, keep_list_item, data_dir, output_file):
        self.title = title
        self.host = host.rstrip('/')
        self.keep_list_item = keep_list_item
        self.data_dir = data_dir
        self.output_file = output_file
        self.paths = {}
        self.tag = None

    def run(self):
        for root, _, files in os.walk(self.data_dir):
            apifiles = [fn for fn in files if fn.endswith('.api')]
            if not apifiles:
                continue
            # noinspection PyTypeChecker
            self.process_folder(root, apifiles)

        self.output()

    def output(self):
        swagger = Swagger(
            swagger="2.0",
            info=Info(
                title=self.title,
                version="0.1"
            ),
            host=self.host,
            basePath="/",
            paths=Paths(self.paths),
        )

        with open(self.output_file, 'w') as fp:
            json.dump(swagger, fp, ensure_ascii=False, sort_keys=True, indent=2)

    def process_folder(self, root, apifiles):
        self.tag = root.lstrip('./')

        actions = collections.OrderedDict()

        # 按名称分组
        for filename in apifiles:
            name = re.sub(r'^[\d_]+-(.*?)\.api', r'\1', filename)
            actions.setdefault(name, []).append(filename)

        for name, filenames in actions.items():
            self.process_action(root, name, filenames)

    def process_action(self, root, apiname, filenames):
        api = Api()
        for filename in filenames:
            api.add_session(self.read_session(Path(root) / filename))

        for seq_no, session in enumerate(api.sessions, 1):
            request = session.request
            response = session.response
            path = (root + '/' + apiname).lstrip('.')

            responses = Responses()
            responses[response.status_code] = openapi.model.Response(
                description='TODO: description',
                # headers=response.headers,
                schema=response.schema,
            )

            operation = Operation({
                "parameters": session.parameters,
                "responses": responses
            })

            self.paths[path] = PathItem({
                request.method.lower(): operation,
            })

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
@click.option('--output', '-o', help='Swagger 文件名.')
def run(title, host, keep_list_item, data_dir, output):
    if not output:
        if title is not None:
            output = 'apiswagger-%s.json' % (re.sub('[^\w.]', '-', title).lower())
        else:
            output = 'apiswagger.json'
    if title is None:
        title = 'API - ApiSwagger'
    apiswagger = ApiSwagger(title, host, keep_list_item, data_dir, output)
    apiswagger.run()


if __name__ == "__main__":
    run()
