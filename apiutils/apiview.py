from urllib.parse import parse_qs

import click
from apiutils import util


class HTTPMessage(object):
    headers = dict()
    body = b''
    decoded_body = ''
    simplified_body = ''

    def parse_body(self, keep_list_item):
        self.decoded_body = util.decode_body(self.headers, self.body)
        self.simplified_body = util.simplify_body(self.decoded_body, keep_list_item)


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


class Response(HTTPMessage):
    def __init__(self, latency, payload):
        self.latency = latency
        self.payload = payload

        self.response_line, self.raw_headers, self.body = util.http_split_message(payload)
        self.headers = util.http_parse_headers(self.raw_headers)
        self.version, self.status_code, self.reason = self.response_line.split(' ', 2)

    def __str__(self):
        return '%s %s' % (self.latency, self.response_line)


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


class ApiViewer(object):
    def __init__(self, keep_list_item, apifiles):
        self.keep_list_item = keep_list_item
        self.apifiles = apifiles

    def run(self):
        for apifile in self.apifiles:
            session = self.read_session(apifile)
            self.print_request(session.request)
            self.print_response(session.response)

    # noinspection PyMethodMayBeStatic
    def print_request(self, request):
        print('# Request\n')
        print(request.request_line)
        print(request.raw_headers)
        if request.body:
            print()
            print(request.simplified_body)
        print()

    # noinspection PyMethodMayBeStatic
    def print_response(self, response):
        print('# Response\n')
        print(response.response_line)
        print(response.raw_headers)
        if response.body:
            print()
            print(response.simplified_body)
        print()

    def read_session(self, apifile):
        fp = open(apifile, 'rb')

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
@click.option('--keep-list-item', '-k', default=3, help='列表中保留的项数.')
@click.argument('apifiles', nargs=-1)
def run(keep_list_item, apifiles):
    viewer = ApiViewer(keep_list_item, apifiles)
    viewer.run()


if __name__ == "__main__":
    run()
