FORMAT: 1A
HOST: http://{host}

# API

文档说明。

修改日志（只保存比较大的修改）：

版本 0.1

* 张三: 初始版本
* 李四: 增加示例

版本 0.2

* 新的修改

**相关人员确认**

* [ ] 张三（编写）： 基本完成
* [ ] 李四（审核）： 安全问题有待加强

# Group 登录


## Login [/pad/login]

:::note
### 注意

着重说明的是密码等绝对不能出现在 URL 中。
:::

### 登录 [POST /login]

+ Request (application/json)

    + Headers

            Authorization: Basic cG9zdG1hbjpwYXNzd29yZA==

    + Body

            {
              "username": "tom",
              "password": "jerry"
            }

+ Response 200 (application/json)

        {
          "code": 200,
          "user": {
            "id": 123456,
            "name": "Tom Cat",
            "age": 3
        }

# Group 基础信息

## 机构 [/orgs]

### 机构列表 [GET /orgs{?type,area}]

+ Parameters
    + `type`: `1` (integer, optional) -- 机构类型
    + `area`: `410101` (integer, optional) -- 行政代码

+ Response 200 (application/json)

        {
          "code": 200,
          "orgs: [
          }
        }