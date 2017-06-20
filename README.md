# API 工具集

主要功能：

* 捕获 HTTP 请求
* 分析 HTTP 请求，生成 API Blueprint 文档
* 从 API Blueprint 文档生成 API 文档
* 生成 Postman 文件，可以导入 Postman

组成

* [x] apicapture -- 捕获 HTTP API 请求
* [x] apiview -- 查看 API 数据文件
* [x] apiswagger -- 从 API 数据文件生成 Swagger 文档
* [x] apischema -- 从 Json 对象生成 JSON Schema（Swagger 中使用）
* [x] apiblue -- 从 API 数据文件生成 API Blueprint 文档
* [x] apiman -- API Blueprint 文档生成 Postman
* [x] apigen -- API 文档辅助工具
* [ ] apimonitor -- 自动监测 API 调用情况

TODO

* [x] apiwatch 可以合并到 apicapture 中

需要的其他工具

* goreplay -- httpcapture 是 goreplay 的插件
* aglio -- 从 API Blueprint 文档生成 API 文档
* [drafter](https://github.com/apiaryio/drafter) -- API Blueprint 文档分析工具
* [blueman](https://github.com/pixelfusion/blueman) -- 从 API Blueprint 文档生成 Postman 文件
* [api-mock](https://github.com/localmed/api-mock) -- Mock Server
* [apiary-cli](https://help.apiary.io/tools/apiary-cli/) -- 

## apicapture

apicapture 作为 goreplay 的插件使用，基本用法如下：

```sh
gor --input-raw :80 --input-raw-track-response --input-raw-realip-header X-Real-IP --output-null --verbose --middleware "apicapture"
```

为了方便使用，可以利用 alias:

```sh
alias api-gor="gor --input-raw :80 --input-raw-track-response --input-raw-realip-header X-Real-IP --output-null --verbose --middleware" 
```

然后上面的命令可以简化为：

```sh
api-gor "apicapture"
```

下面的示例均假定已经定义了 api-gor。

**监视 api 调用情况**

```sh
api-gor "apicapture -u /interface/*"
```

参数:

* `-u`, `--url`: URL 过滤（支持 `*` `?` `[abc]`)
* `-h`, `--host`: HOST 过滤（支持 `*` `?` `[abc]`)

**监视 api 调用并输出详细信息**

```sh
api-gor "apicapture -w -u /interface/*"
```

参数：

* `-w`, `--watch`: 输出 api 详细信息
* `-k`, `--keep-list-item`: 指定 api 数据中的列表保留的项数（为了避免过多数据干扰）。


**保存 api 文件**

```sh
api-gor "apicapture -s api_save_dir -u /interface/*"
```

参数：

* `-s`, `--save-dir`: 指定 api 数据文件保存的目录

说明，`-s` 和 `-w` 可以同时使用：

```sh
api-gor "apicapture -w -s api_save_dir -u /interface/*"
```

**apicapture 的命令行参数**

```sh
$ apicapture --help
Usage: apicapture [OPTIONS]

Options:
  -s, --save-dir TEXT           保存 API 数据文件目录.
  -w, --watch                   是否输出详细信息.
  -h, --host TEXT               host 过滤（允许指定多个）.
  -u, --url TEXT                url 过滤（允许指定多个）.
  -k, --keep-list-item INTEGER  列表中保留的项数.
  -c, --cache-size INTEGER      Request 缓存个数.
  -d, --debug                   是否输出调试信息.
  -v, --version                 版本信息.
```

## apiview

用法：

```
apiview <apifile> ...
```

## apiswagger

用法：

```sh
$ apiswagger
```

帮助信息：

```sh
$ apiswagger --help
Usage: apiswagger [OPTIONS]

Options:
  -t, --title TEXT              API 标题.
  -h, --host TEXT               API 主机.
  -k, --keep-list-item INTEGER  列表中保留的项数.
  -d, --data-dir TEXT           API 数据文件目录.
  -o, --output TEXT             Swagger 文件名.
  --help                        Show this message and exit.
```

生成的 Swagger 文件为 JSON 格式，即 swagger.json，要转成 swagger.yaml，需要执行下面的命令：

```sh
remarshal -if json -of yaml -i apiswagger.json > apiswagger.yaml
```

## apischema

使用方法：

```sh
$ cat example.json | apischema
```

## apigen

使用方法：

```sh
$ apigen examples/apigen.yaml
```

参见示例文件：

* `examples/apigen.yaml`
* `examples/apigen-simple.yaml`

## apiblue

用法:

    apiblue --host http://api.sportsdatas.cn

查看帮助：

    $ apiblue --help
    Usage: apiblue [OPTIONS]
    
    Options:
      -h, --host TEXT               指定 API 主机
      -k, --keep-list-item INTEGER  列表中保留的项数.
      -d, --data-dir TEXT           API 数据文件目录
      -o, --output FILENAME         API Blueprint 文件名.
      --help                        Show this message and exit.


## aglio

生成 api 文档:

    aglio -i api.apib -o api.html

## apiary-cli

生成 api 文档（生成的文档需要联网）:

    apiary preview --path=api.apib --output=apiary.html

启动本地服务器：

    apiary preview --path=api.apib --server --port=8080

参数：

* `--path`: 指定 apib 文件（缺省为 apiary.apib）。

## 生成 Postman 文件:

### 使用 apiman

    apiman
    apiman -t 'PAD v1.1.12'

### 使用 drafter + blueman

配合 drafter 使用：

    drafter -f json -t ast -o api.json api.apib
    blueman.phar convert --output=api-postman.json api.json

生成 Postman 文档时可以重新指定 host：

    blueman.phar convert --output=api-postman.json --host=http://api.sportsdatas.cn/v2 api.json

## 启用 Mock Server:

    api-mock api.apib

## `.api` 文件

**文件名**

```
<path>/<to>/<time>-<name>
```

其中：

* time: HTTP 请求的时间，格式 `YYYYmmdd_HHMMSS`
* name: HTTP 路径中

**文件格式**

```
Request-Time: 2017-02-16 10:02:39       # HTTP 请求的时间
Latency: 3.142                          # 响应延迟，单位: 秒

Request <Length>
<Request>

Response <Length>
<Response>
```

## 问题

**没有给力的 API Blueprint 到 Postman 的转换工具**

如果考虑自己实现，下面是一些参考资料：

* drafter -- API Blueprint 分析工具
* [API Elements](http://api-elements.readthedocs.io/en/latest/) -- drafter 分析结果的的文档
* [Travelogue of Postman Collection Format v2](http://blog.getpostman.com/2015/06/05/travelogue-of-postman-collection-format-v2/) -- Postman 文件格式
* [flask2postman](https://github.com/numberly/flask2postman)

实现思路一： 利用 drafter 的分析结果

    API Blueprint --(drafter)--> YAML/JSON --()--> Postman 文件 

实现思路二： 利用 aglio 的分析结果

    API Blueprint --(aglio)--> HTML --()--> Postman 文件 

实现思路三： 直接分析 .api 文件

    apicapture --> .api --> Postman 文件

优点：

* 不依赖与第三方的代码

缺点：

* 不能分析 API Blueprint 文档

## 参考

* [API Blueprint](https://apiblueprint.org/)
* [API Blueprint Tools](https://apiblueprint.org/tools.html)
