---
domain: # 领域
tags: # 自定义标签
-
datasets: # 关联数据集
  evaluation:
  test:
  train:
models: # 关联模型

# 启动文件
# deployspec:
#   entry_file: main.py
license: Apache License 2.0
---
# File Explorer

## 简介

只需添加几行代码，就能为您的 FastAPI 云服务添加一个文件资源管理器界面。

支持的功能：

- 列出目录内容
- 文件详细信息
- 创建文件/文件夹
- 上传文件
    - 大文件自动分块上传
- 下载文件
    - 大文件自动分块下载
    - 支持下载压缩包
- 搜索文件
- 跟踪符号链接

## 快速开始

### 克隆本仓库

```bash
cd path/to/your/project
git submodule add https://github.com/Jerry-Wu-GitHub/file-explorer.git file_explorer
git submodule update --remote
```

### 安装依赖

```bash
python -m pip install -r "file_explorer/requirements.txt"
```

### 注册路由

```python
from fastapi import FastAPI
from file_explorer import lifespan, get_router, register_exception_handlers

app = FastAPI(lifespan=lifespan)
register_exception_handlers(app)
app.include_router(get_router(prefix="子页面前缀"))
```

## 示例

见 [`main.py`](main.py) 。