"""
说明： Goreplay 中 Response 的 timestamp 和 Request 一样，不必要特别记录和处理
"""

import binascii
import collections
import fnmatch
import logging
import os
import sys
from pathlib import Path

import apiutils
import click
from apiutils import util


class Request(object):
    def __init__(self, timestamp, payload):
        self.timestamp = round(int(timestamp) / 1000000000, 3)
        self.payload = payload

        self.request_line, raw_headers, self.body = util.http_split_message(payload)
        self.raw_headers = util.hack_gor_real_ip(raw_headers)
        self.headers = util.http_parse_headers(self.raw_headers)
        self.method, self.url, self.version = self.request_line.split(' ')

        self.host = self.headers.get('host', 'n/a')
        self.path, _, self.query = self.url.partition('?')

    def __str__(self):
        return '%s %s' % (util.strftime(self.timestamp), self.request_line)

    def filter_by_hosts(self, hosts):
        if not hosts:
            return True
        for pattern in hosts:
            if fnmatch.fnmatchcase(self.host, pattern):
                return True
        return False

    def filter_by_urls(self, urls):
        if not urls:
            return True
        for pattern in urls:
            if fnmatch.fnmatchcase(self.url, pattern):
                return True
        return False


class Response(object):
    def __init__(self, latency, payload):
        self.latency = round(int(latency) / 1000000000, 3)
        self.payload = payload

        self.response_line, self.raw_headers, self.body = util.http_split_message(payload)
        self.headers = util.http_parse_headers(self.raw_headers)
        self.version, self.status_code, self.reason = self.response_line.partition(' ')

    def __str__(self):
        return '%s %s' % (self.latency, self.response_line)


class APICapture(object):
    requests = collections.OrderedDict()

    def __init__(self, hosts, urls, save_dir, watch, keep_list_item, cache_size):
        self.hosts = hosts
        self.urls = urls
        self.save_dir = Path(save_dir) if save_dir else None
        self.watch = watch
        self.keep_list_item = keep_list_item
        self.cache_size = cache_size

    def run(self):
        logging.info('apicapture-%s started.' % apiutils.__version__)
        logging.info('hosts: %s', list(self.hosts))
        logging.info('urls: %s', list(self.urls))
        for line in sys.stdin:
            # noinspection PyBroadException
            try:
                packet = binascii.unhexlify(line.rstrip())
                self.parse_gor_packet(packet)
            except:
                logging.exception('Unknown error: %s', line)
        logging.info('stopped.')

    def parse_gor_packet(self, packet):
        header, _, payload = packet.partition(b'\n')

        header = header.decode()
        tokens = header.split(' ')
        message_type = tokens[0]
        if message_type == '1':
            uuid, timestamp = tokens[1:]
            self.parse_request(uuid, timestamp, payload)
        elif message_type == '2':
            uuid, timestamp, latency = tokens[1:]
            # 说明： Response 的 timestamp 和 Request 一样，不必要特别记录和处理
            self.parse_response(uuid, latency, payload)
        else:
            logging.warning('Unknown gor message type: %s', packet)

    def parse_request(self, uuid, timestamp, payload):
        request = Request(timestamp, payload)

        # host 过滤
        if not request.filter_by_hosts(self.hosts):
            logging.debug('host does not match: %s', request)
            return

        # URL 过滤
        if not request.filter_by_urls(self.urls):
            logging.debug('url does not match: %s', request)
            return

        self.requests[uuid] = request
        if len(self.requests) > self.cache_size:
            _, discard = self.requests.popitem(False)
            logging.warning('discard request for cache is full: %s', discard)

    def parse_response(self, uuid, latency, payload):
        response = Response(latency, payload)

        request = self.requests.pop(uuid, None)
        if not request:
            return

        logging.info('%s - %s', request.request_line, response.response_line)
        if self.save_dir:
            self.save_api(request, response)
        if self.watch:
            self.output_api(request, response)

    def save_api(self, request, response):
        filepath = self.save_dir / request.path.lstrip('/')
        path = filepath.parent
        request_time = util.strftime(request.timestamp, '%Y%m%d_%H%M%S')
        name = '%s-%s.api' % (request_time, filepath.name)
        filepath = path / name
        if not path.exists():
            path.mkdir(0o777, True)
        lines = [
            ('Request-Time: %s\r\n' % util.strftime(request.timestamp)).encode(),
            ('Latency: %.3f\r\n' % response.latency).encode(),
            b'\r\n',
            ('Request %d\r\n' % len(request.payload)).encode(),
            request.payload,
            b'\r\n',
            ('Response %d\r\n' % len(response.payload)).encode(),
            response.payload,
        ]
        with filepath.open('wb') as fp:
            fp.writelines(lines)

    def output_api(self, request, response):
        lines = [
            '',
            '# Request',
            '',
            request.request_line,
            '',
            request.raw_headers,
            '',
            self.parse_body(request.headers, request.body),
            '',
            '# Response',
            '',
            response.response_line,
            '',
            response.raw_headers,
            '',
            self.parse_body(response.headers, response.body),
            '',
        ]
        sys.stderr.write('\n'.join(lines))

    def parse_body(self, headers, body):
        return util.simplify_body(util.decode_body(headers, body), self.keep_list_item)


@click.command()
@click.option('--save-dir', '-s', default=None, help='保存 API 数据文件目录.')
@click.option('--watch', '-w', is_flag=True, help='是否输出详细信息.')
@click.option('--host', '-h', multiple=True, help='host 过滤（允许指定多个）.')
@click.option('--url', '-u', multiple=True, help='url 过滤（允许指定多个）.')
@click.option('--keep-list-item', '-k', default=1, help='列表中保留的项数.')
@click.option('--cache-size', '-c', default=128, help='Request 缓存个数.')
@click.option('--debug', '-d', is_flag=True, help='是否输出调试信息.')
@click.option('--version', '-v', is_flag=True, is_eager=True, help='版本信息.')
def run(host, url, save_dir, watch, keep_list_item, debug, cache_size, version):
    if version:
        print('apicapture %s' % apiutils.__version__)
        return

    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=log_level, format=log_format)

    if save_dir:
        os.makedirs(save_dir, 0o777, True)

    capture = APICapture(host, url, save_dir, watch, keep_list_item, cache_size)
    capture.run()


if __name__ == "__main__":
    run()
