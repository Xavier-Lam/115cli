# 115cli

[![PyPI version](https://img.shields.io/pypi/v/115cli.svg)](https://pypi.org/project/115cli/)
[![test](https://github.com/Xavier-Lam/115cli/actions/workflows/test.yml/badge.svg)](https://github.com/Xavier-Lam/115cli/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/Xavier-Lam/115cli/branch/master/graph/badge.svg)](https://codecov.io/gh/Xavier-Lam/115cli)

**115cli** 是一个非官方的 [115.com](https://115.com) 网盘命令行工具和 *Python* 库, 提供常用的文件操作命令行接口, 同时提供一个高级API封装供 *Python* 项目使用.

在使用本项目前, 请仔细阅读[免责声明](#免责声明).

## 安装

推荐使用 pip 安装:

```bash
pip install 115cli
```

## 快速上手(CLI)

先用 `115cli auth` [登录](#认证) (目前只支持从浏览器复制的 cookie 登录), 认证成功后就可以用 `115cli` 命令操作你的 115 云盘了.

常见示例:

```bash
# 使用 cookie 登录
115cli login cookie "UID=xxx; CID=xxx; SEID=xxx; KID=xxx"

# 账户信息
115cli account

# 目录
115cli ls /
115cli ls /path/to/dir -l

# 文件操作
115cli mkdir /new-folder
115cli cp /src/file.txt /dst/
115cli mv /old/path /new/path
115cli rm /path/to/file
115cli rm -r /path/to/dir
115cli find /search/path keyword

# 查看文件信息和获取下载地址
115cli stat /path/to/file
115cli url /path/to/file
115cli url --format aria2c /path/to/file

# 下载
115cli fetch /path/to/file.mp4
115cli fetch /path/to/file.mp4 -o /local/save/path.mp4

# 上传(支持秒传)
115cli upload /local/file.txt /remote/dir/file.txt
# 仅秒传
115cli upload --instant-only /local/file.txt /remote/dir/file.txt
# 文件夹上传
115cli upload /local/folder/ /remote/dir/

# 离线下载
115cli download quota
115cli download list
115cli download add "https://example.com/file.mp4"
115cli download delete <info_hash>
```

> 注意: 某些创建云下载任务的操作可能会触发图形验证码, 目前客户端不支持处理验证码.

### 认证(Cookie)

本项目目前只支持通过浏览器拿到的 cookie 登录.登录时需要提供 `UID`, `CID`, `SEID` 和 `KID` 四个 cookie 值.

```bash
115cli auth cookie "UID=xxx; CID=xxx; SEID=xxx; KID=xxx"
```

## Client API

本项目提供一个高级的 *Python* API 客户端,你可以在自己的项目中直接使用:

```python
from cli115.auth import CookieAuth
from cli115.client import create_client

auth = CookieAuth(
	uid="xxx",
	cid="xxx",
	seid="xxx",
	kid="xxx"
)
client = create_client(auth)

# 列目录
entries = client.file.list("/")
for entry in entries:
	print(entry.name, entry.id)

# 文件信息
info = client.file.info("/path/to/file.txt")
print(info.name, info.size, info.sha1)

# 获取下载信息
dl = client.file.url("/path/to/file.txt")
print(dl.url)

# 下载
with client.file.open("/path/to/file.txt") as rf:
    data = rf.read(1024)  # 仅下载前1024字节

# 上传
result = client.file.upload("/remote/dir/", "/local/file.txt")

# 添加云端下载任务
client.download.add_url("https://example.com/file.mp4")
tasks = client.download.list()
```

## 未来计划

项目仍在早期,计划包括但不限于:

- 更完善的云下载管理 (包括验证码处理)
- 多线程下载加速
- 回收站管理
- 手机验证码登录 (补充 cookie 登录)

## 免责声明

这是一个非官方的工具, 与 *115.com* 或其母公司无任何关联. 使用风险自负, 作者不对账号被封, 数据丢失等后果负责.

你可能会遇到*阿里云 WAF* 的封禁 (机制和后果尚不明确), 被封禁后可能需要等待一段时间再重试, 网页端也会受到影响.
