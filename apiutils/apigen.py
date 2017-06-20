# -*- coding: utf-8 -*-

"""API 文档辅助生成工具

输入文件格式 yaml
"""
import json
from textwrap import indent
from urllib.parse import parse_qs

import click
import pyaml
import sys
import yaml
from apiutils import util
from apiutils.apischema import build_schema


class Defination(object):
    """
    支持的格式：

    id: 对象标识
    *id: 对象标识(123)
    *id: 对象标识(123:integer)
    """
    required = 'false'
    default = None
    type = "string"
    description = "N/A"

    def __init__(self, name, defination='N/A'):
        if name.startswith('*'):
            name = name[1:]
            self.required = 'true'
        self.name = name
        if defination.endswith(')'):
            description, _, default = defination[:-1].rpartition('(')
            if ':' in default:
                default, _, type = default.rpartition(':')
                if type in ("string", "number", "boolean", "integer"):
                    pass
                elif type in ("int",):
                    type = "integer"
                elif type in ("float",):
                    type = "number"
                elif type in ("bool",):
                    type = "boolean"
                self.type = type
            else:
                self.type = util.guess_value_type(default)
            self.default = default
            self.description = description
        else:
            self.description = defination


class ApiGen(object):
    def __init__(self, ofile):
        self.ofile = ofile

        self.global_definations = {}
        self.definations = {}
        self.descriptions = {}

        # 用于合并相同 path 的不同 method
        self.last_path = None

    def output(self, *args, **kwargs):
        kwargs.update(file=self.ofile or sys.stdout)
        print(*args, **kwargs)

    def process(self, srcfile):
        with open(srcfile, 'r', encoding='utf-8') as stream:
            for obj in yaml.load_all(stream):
                self.process_obj(obj)

    def process_obj(self, obj):
        self.definations = self.global_definations.copy()

        definations = obj.get('definations', {})
        for name, defination in definations.items():
            defination = Defination(name, defination)
            self.definations[defination.name] = defination

        request = obj.get('request')
        if not request:
            # 对于没有 request 的 definations，认为是全局的
            self.global_definations = self.definations.copy()
            return

        responses = obj.get('responses')
        if not responses:
            self.output('格式错误， 没有 responses')
            return

        self.descriptions = { name: defination.description
                              for name, defination in self.definations.items() }

        self.process_request(request)
        self.output('      responses:')
        for name, response in sorted(responses.items()):
            self.output('        "%s":' % name)
            self.process_response(response)

    def process_request(self, request):
        summary = request.get('summary')
        description = request.get('description', 'N/A')
        method = request.get('method').lower()
        url = request.get('url')
        path, _, query = url.partition('?')

        # 合并 path 的不同 method
        if path != self.last_path:
            self.output('  %s:' % path)
            self.last_path = path

        self.output('    %s:' % method)
        self.output('      summary:', summary)
        self.output('      description:', self.process_description(description))

        tags = request.get('tags')
        if tags:
            self.output('      tags:')
            for tag in tags:
                self.output('        -', tag)

        parameters = []

        # 分析 path 中的参数
        for name in path.split('{')[1:]:
            if '}' in name:
                name = name.partition('}')[0]
            defination = self.get_defination(name)
            # 注意: path 中的 required 必须是 true
            defination.required = True
            parameters.append(('path', defination))

        # 分析 query 中的参数
        for name, value in sorted(parse_qs(query).items()):
            if len(value) == 1:
                value = value[0]
            defination = self.get_defination(name)
            defination.type = util.guess_value_type(value)
            parameters.append(('query', defination))

        # 分析 form 中的参数，仅支持 form-urlencoded
        form = request.get('form')
        if form:
            for name, value in sorted(parse_qs(form).items()):
                if len(value) == 1:
                    value = value[0]
                defination = self.get_defination(name)
                defination.type = util.guess_value_type(value)
                parameters.append(('formData', defination))

        if parameters:
            self.output('      parameters:')
            for in_, defination in parameters:
                self.output('        - name:', defination.name)
                self.output('          in:', in_)
                self.output('          type:', defination.type)
                if defination.default is not None:
                    self.output('          default:', defination.default)
                self.output('          required:', defination.required)
                self.output('          description:', defination.description)

        body = request.get('body')
        if body and form:
            print('body 和 form 不能同时存在.')
            return

        if body:
            schema = build_schema(json.loads(body), self.descriptions)
            self.output('        - name: body')
            self.output('          in: body')
            self.output('          required: true')
            self.output('          schema:')
            self.output(indent(pyaml.dump(schema), '            '), end='')

    def get_defination(self, name):
        if name in self.definations:
            defination = self.definations.get(name)
        else:
            defination = Defination(name)
        return defination

    def process_response(self, response):
        description = response.get('description', 'N/A')
        self.output('          description:', self.process_description(description))
        body = response.get('body')
        if body:
            schema = build_schema(json.loads(body), self.descriptions)
            self.output('          schema:')
            self.output(indent(pyaml.dump(schema), '            '), end='')

    def process_description(self, description):
        if '\n' in description:
            description = '|\n' + indent(description, '        ')

        return description


@click.command()
@click.option('--ofile', '-o', type=click.File('w', encoding='utf-8'), help='输出文件.')
@click.argument('srcfiles', nargs=-1)
def run(ofile, srcfiles):
    apigen = ApiGen(ofile)
    for srcfile in srcfiles:
        apigen.process(srcfile)


if __name__ == "__main__":
    run()
