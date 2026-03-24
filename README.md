# 115cli

[![PyPI version](https://img.shields.io/pypi/v/115cli.svg)](https://pypi.org/project/115cli/)
[![test](https://github.com/Xavier-Lam/115cli/actions/workflows/test.yml/badge.svg)](https://github.com/Xavier-Lam/115cli/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/Xavier-Lam/115cli/branch/master/graph/badge.svg)](https://codecov.io/gh/Xavier-Lam/115cli)

An unofficial CLI tool and *Python* library for [115.com](https://115.com) cloud storage. It provides a command-line interface for common file operations and a higher-level *Python* API client that can be used as a library in your own code.

Read [disclaimer](#disclaimer) carefully before using this tool.

[中文版 README](README.zh.md)

## Installation

```bash
pip install 115cli
```

## Usage

### CLI

After [authenticating](#authentication) with `115cli auth`, you can use the `115cli` command to interact with your 115 cloud storage. Here are some examples of available commands:

```bash
# List files
115cli ls /
115cli ls /path/to/dir -l

# File operations
115cli mkdir /new-folder
115cli cp /src/file.txt /dst/
115cli mv /old/path /new/path
115cli rm /path/to/file
115cli rm -r /path/to/dir
115cli find /search/path keyword

# File info and download
115cli info /path/to/file
115cli download-info /path/to/file
115cli download-info --format aria2c /path/to/file

# Upload
115cli upload /local/file.txt /remote/dir/

# Cloud download (offline download)
115cli download quota
115cli download list
115cli download add "https://example.com/file.mp4"
115cli download delete <info_hash>
```

> **Note:** Creating cloud download tasks may trigger a captcha challenge. This is currently not supported by the client.

#### Authentication

115cli currently only supports cookie-based authentication. Obtain your cookies from the browser after logging into [115.com](https://115.com). You need the `UID`, `CID`, `SEID`, and `KID` cookie values.

```bash
115cli auth cookie <user_name> "UID=xxx; CID=xxx; SEID=xxx; KID=xxx"
```

### Python API

The package also exposes a higher-level Python API client that you can use in your own projects:

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

# List directory
entries, pagination = client.file.list("/")
for entry in entries:
    print(entry.name, entry.id)

# Get file info
info = client.file.info("/path/to/file.txt")
print(info.name, info.size, info.sha1)

# Download info
dl = client.file.download_info("/path/to/file.txt")
print(dl.url)

# Upload
result = client.file.upload("/remote/dir/", "/local/file.txt")

# Cloud download
client.download.add_url("https://example.com/file.mp4")
tasks, _ = client.download.list()
```

> This project is in an early stage of development, it may subject to breaking changes in the future.

## Future Plans

The project aims to cover the core features of 115 cloud storage. Planned additions include:

- **Instant upload:** Skip uploading files that already exist in the cloud using SHA-1 matching.
- **Cloud download management:** Full management of offline download tasks including captcha support.
- **Multi-threaded download:** A `115cli fetch` command to download files with multi-thread acceleration.
- **Recycle bin management:** List, restore, and permanently delete items from the recycle bin.
- **Mobile phone authentication:** SMS-based login in addition to cookie auth.

## Disclaimer

This is an **unofficial** client for *115.com* and is not affiliated with, endorsed by, or associated with *115.com* or its parent company in any way.

Use at your own risk. The authors are not responsible for any account suspension, data loss, or other consequences arising from the use of this software. The API may change at any time without notice, which could break this tool.

You may encounter *Aliyun WAF* blocks when using the library, the mechanism and consequences are currently unknown. It may relate to the frequency of API calls. After being blocked, you may need to wait for a while before retrying, the official web interface may also be affected during the block period.
