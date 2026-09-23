# 第 3 周技术总结：FastAPI + SSE + Docker + Linux

> 16 周 AI Agent 应用开发学习记录 · 第 3 周
> 关键词：FastAPI、Pydantic、SSE 流式返回、Docker、Linux 命令行

---

## 本周概览

前两周写的都是**脚本**——运行一次，跑完退出。从这周开始转变为**服务**：一个常驻进程，启动后一直运行，来一个请求处理一个。

第 2 周我站在 HTTP 的**客户端**位置（用 httpx 发请求），这周站到了**服务端**位置（用 FastAPI 收请求）。之前学的状态码、请求头、JSON 响应，现在要自己实现。

| 小节 | 内容 | 产出 |
|---|---|---|
| 1 | FastAPI 基础 | 能被访问的 HTTP 服务 |
| 2 | Pydantic 数据模型 | 请求体自动校验 |
| 3 | SSE 流式返回 | 逐字推送的聊天接口 |
| 4 | Docker | 可 `docker run` 的镜像 |
| 5 | Linux 命令行 | 能进容器排查问题 |

**本周最终产出**：一个 `POST /chat/stream` 接口，接收 JSON 请求体，以 SSE 协议逐字推送 JSON 格式的回复，末尾附带 token 统计块；整个服务打包成 Docker 镜像，一条命令即可在任意机器上运行。

**代码仓库**：`https://github.com/Ruiwen-ZHANG/ai-agent-learning`

---

## 第一章 FastAPI 基础

### 1.1 两个包，各管一件事

```bash
uv pip install fastapi uvicorn
```

| 包 | 职责 |
|---|---|
| `fastapi` | 框架本身：路由、参数解析、数据校验、自动生成文档 |
| `uvicorn` | ASGI 服务器：真正监听端口、接收 TCP 连接、解析 HTTP 报文 |

FastAPI 只定义"收到请求后怎么处理"，它自己不会监听端口。两者的关系类似于「业务逻辑」与「运行时」，必须配合使用。

### 1.2 启动服务

```bash
uvicorn main:app --reload
```

这条命令的三个部分：

- `main` —— 模块名，即 `main.py`（不带 `.py` 后缀）
- `app` —— 该模块里 `FastAPI()` 实例的变量名
- `--reload` —— 保存代码后自动重启，仅用于开发环境

**关键认知：`模块名:对象名` 是相对于终端当前目录解析的。** 这一点在本周造成了两次启动失败，详见第六章错误 8。

### 1.3 路由与装饰器

```python
from fastapi import FastAPI

app = FastAPI()                      # 创建应用实例，后面所有路由都挂在它上面


@app.get("/")                        # 装饰器：把下面的函数注册为 GET / 的处理函数
async def root():                    # async def 让它成为协程函数，可以在内部 await
    return {"message": "hello"}      # 返回 dict，FastAPI 自动序列化成 JSON 响应
```

装饰器 `@app.get(...)` 做的事情是：把函数登记进路由表，键是「方法 + 路径」。请求到达时，FastAPI 查表找到对应函数并调用。

### 1.4 自动文档

服务启动后访问 `http://127.0.0.1:8000/docs`，能看到一个交互式 API 文档页面（Swagger UI）。

它有两个实用价值：

1. **可以直接发请求测试**，不用写 curl 命令，POST 带 JSON 时尤其方便（Windows PowerShell 的引号转义很麻烦）。
2. **它展示的是服务端实际加载的代码**。当你怀疑代码改动没生效时，看 `/docs` 里的请求体结构比看源文件更可靠。

> **排查技巧**：本周遇到过一次「代码明明改了但行为是旧的」。原因是存在重复路由——FastAPI 遇到路径相同的两个路由**不报错，只使用第一个**。通过 `/docs` 显示的请求体结构与源码不符，才定位到问题。

---

## 第二章 Pydantic 数据模型

### 2.1 它解决什么问题

第 1 周学的类型注解只是给 IDE 看的提示，运行时完全不生效。Pydantic 把注解变成了**运行时的校验规则**。

```python
from pydantic import BaseModel      # 所有数据模型都继承自 BaseModel


class ChatRequest(BaseModel):
    role: str                        # 必填字段，且必须能转成字符串
    content: str                     # 必填字段
```

在 FastAPI 中使用：

```python
@app.post("/chat/stream")
async def chat_stream(receive: ChatRequest):
    # 参数类型注解写成模型类，FastAPI 就知道要从"请求体"里读 JSON
    # 校验通过后，receive 是一个 ChatRequest 对象，用点号访问字段
    return {"echo": receive.content}
```

三件事自动发生：

1. 从请求体解析 JSON
2. 按模型定义校验字段的存在性与类型
3. 校验失败**直接返回 422，函数根本不会被执行**

### 2.2 422 报错信息怎么读

故意少传一个字段，响应是这样：

```json
{
  "detail": [
    {
      "loc": ["body", "content"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

`loc` 是定位路径，从外到内：请求体 → content 字段。嵌套模型时路径会更长，例如 `["body", "messages", 0, "role"]` 表示「请求体 → messages 数组 → 第 0 个元素 → role 字段」。

> 这个路径在排查时很有用：**同一个非法请求，报错路径不同，就能判断服务端实际加载的是哪个模型版本。**

### 2.3 为什么 422 能正常返回，而流式接口的错误不能

这是本周一个重要的认知，把它记在这里，第三章会再次用到。

HTTP 响应的发送顺序是：**状态行（含状态码）→ 响应头 → 空行 → 响应体**。

Pydantic 校验发生在**函数执行之前**，此时状态行还没发出，所以可以正常返回 422。而流式接口一旦开始推送数据，状态码早已发出，无法再改。

### 2.4 `if __name__ == "__main__"` 的意义

在 `models.py` 里写测试代码时踩过一个坑：直接写在模块顶层的测试代码，会在被 `import` 时也执行一遍，导致启动服务时打印出一堆测试输出。

```python
if __name__ == "__main__":
    # 只有直接运行 python models.py 时，这里才会执行
    # 被别的文件 import 时，__name__ 是模块名而不是 "__main__"，这段会跳过
    print(ChatRequest(role="user", content="test"))
```

它解决的是「**同一个文件既要能单独运行，又要能被别人 import**」的矛盾。

**验收标准有两条**，缺一不可：
- `python week3/models.py` 能看到完整测试输出
- `uvicorn week3.main:app --reload` 的启动日志里没有任何测试输出

---

## 第三章 SSE 流式返回

### 3.1 为什么需要

非流式接口的体验：

```
用户提问 → 等 10 秒（屏幕空白）→ 一次性收到完整回答
```

流式接口的体验：

```
用户提问 → 0.5 秒后开始逐字蹦出 → 边生成边显示
```

**总耗时一样，但体验差别巨大。** 用户在第 0.5 秒就得到反馈，而且可以边读边等。

### 3.2 SSE 协议格式

Server-Sent Events 的本质是「一问多答」：连接保持打开，服务器想发就发。

```
data: 第一块内容\n\n
data: 第二块内容\n\n
data: [DONE]\n\n
```

三条硬性规则：

1. 每块以 `data: ` 开头
2. 每块以**两个换行符 `\n\n`** 结尾，这是消息分隔符，少一个客户端会一直等
3. 响应头必须是 `Content-Type: text/event-stream`

### 3.3 生成器：流式的基础

| | `return` | `yield` |
|---|---|---|
| 执行后 | 函数**结束** | 函数**暂停**，保留现场 |
| 返回 | 一次性给全部 | 一次给一个 |
| 内存 | 全部数据都在内存里 | 一次只有一个 |

「暂停」这个特性是关键——函数的执行被切成了若干段，由调用方控制什么时候继续。如果用普通函数，必须先把所有内容生成完才能返回，那就不是流式了。

### 3.4 数据流向：谁负责什么

这是本周理解上卡住最久的一点，单独画出来：

```
客户端发来 JSON
  → 接口函数的参数 receive（Pydantic 已解析好）
  → 调用生成器时把 receive.content 传进去        ← 接口函数负责「传进去」
  → 生成器内部拼回复、逐字构造 JSON、yield        ← 生成器负责「吐出来」
  → StreamingResponse 把每次 yield 的内容发给客户端
```

**结论：生成器里 yield 什么，客户端就收到什么。接口函数不需要接收生成器的输出，也不需要 print 或 return 它。**

### 3.5 任务 4 完整实现：JSON 格式的流

纯文本的 `data: 你` 只能表达一种信息，客户端无法区分正文、错误和结束信号。真实的大模型 API（OpenAI、Anthropic）都让每个事件的 `data` 部分放一个 JSON 对象，用 `type` 字段区分类型。

```python
async def generate_json_text(content):
    """
    异步生成器：把模拟回复逐字包成 JSON 后以 SSE 格式推送

    参数 content 是用户发来的消息内容，由接口函数传入
    """
    # f-string 把用户的消息拼进模拟回复里
    # 真实场景这里会替换成调用大模型的流式接口，其余结构基本不变
    reply = f"收到你的问题：{content}，我正在思考"

    for char in reply:                                   # 逐字符遍历回复
        data = {"type": "delta", "content": char}        # 事件格式：类型 + 这一个字
        text = json.dumps(data, ensure_ascii=False)      # 转成 JSON 字符串
        # ensure_ascii=False 让中文正常显示，不加会变成 \u4f60 形式
        # 绝对不能传 indent 参数，那会产生多行 JSON，破坏 SSE 的单行约束
        yield f"data: {text}\n\n"                        # 按 SSE 格式发出，结尾两个换行
        await asyncio.sleep(0.5)                         # 模拟生成延迟
        # 必须用 asyncio.sleep，用 time.sleep 会阻塞整个事件循环

    yield "data: [DONE]\n\n"                             # 结束标志
```

接口部分：

```python
@app.post("/chat/stream")                     # 接收请求体必须用 POST，GET 一般不带请求体
async def chat_stream(receive: ChatRequest):
    return StreamingResponse(
        generate_json_text(receive.content),  # 把用户消息传给生成器
        media_type="text/event-stream",       # 告诉客户端这是 SSE 流
    )
```

**运行结果**：

```
data: {"type": "delta", "content": "收"}

data: {"type": "delta", "content": "到"}

...

data: [DONE]
```

### 3.6 两个格式陷阱

**陷阱一：JSON 必须是单行。**

`json.dumps` 默认输出单行，字符串内部的换行会被转义成 `\n` 两个字符，所以天然安全。但一旦传了 `indent=2`：

```
data: {
  "type": "delta",
  "content": "收"
}
```

SSE 是**按行解析**的，只有以 `data:` 开头的行才算数据。后面三行没有前缀，会被丢弃。客户端最终只拿到一个 `{`，`json.loads("{")` 直接报错。

**陷阱二：`[DONE]` 不是合法 JSON。**

方括号在 JSON 里表示数组，里面的 `DONE` 既不是带引号的字符串，也不是数字或布尔值。客户端必须**先判断是不是 `[DONE]`，再做 `json.loads`**，否则抛 `JSONDecodeError`。

也可以改用 `{"type": "done"}` 让格式统一，两种方案选一种并保持一致即可。

### 3.7 任务 5 完整实现：usage 统计块

调用商用 API 时计费依据是 token 数。非流式接口直接在响应里返回 usage，但流式接口是一块块吐的，**`completion_tokens` 只有全部生成完才知道，所以统计块只能放在最后**。

（`prompt_tokens` 其实一开始就能算出来，真正要等的是 completion 部分。）

```python
async def generate_json_text(content):
    reply = f"收到你的问题：{content}，我正在思考"

    # token 估算方法：按 1 个字符算 1 个 token
    # 与真实分词有偏差，中文接近、英文偏大，mock 场景够用
    # 精确做法是用 tiktoken 分词
    prompt_tokens = len(content)         # 输入的 token 数，一开始就能算
    completion_tokens = 0                # 计数器，循环前归零

    for char in reply:
        completion_tokens += 1           # 每发一个字加 1
        # 这里用计数器而不是 len(reply)，是为了对齐真实场景：
        # 换成真实大模型后，回复是一块块流过来的，不存在完整的 reply 变量
        data = {"type": "delta", "content": char}
        text = json.dumps(data, ensure_ascii=False)
        yield f"data: {text}\n\n"
        await asyncio.sleep(0.5)

    total_tokens = completion_tokens + prompt_tokens

    usage = {                            # 统计块，注意缩进在 for 循环外面
        "type": "usage",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    usage_json = json.dumps(usage, ensure_ascii=False)
    yield f"data: {usage_json}\n\n"

    yield "data: [DONE]\n\n"
```

**事件顺序必须是：`delta` × N → `usage` → 结束信号。**

**实测结果**（请求 `{"role": "user", "content": "什么是SSE"}`）：

```
data: {"type": "delta", "content": "收"}
...共 19 条 delta...
data: {"type": "delta", "content": "考"}

data: {"type": "usage", "prompt_tokens": 6, "completion_tokens": 19, "total_tokens": 25}

data: [DONE]
```

核对：「什么是SSE」6 个字符；「收到你的问题：」7 个 + 「什么是SSE」6 个 + 「，我正在思考」6 个 = 19 个。中文标点各算 1 个字符。

### 3.8 流式接口的错误处理

**一旦开始推流，状态码就定了，无法再改成 500。** 因为响应头在第一块数据之前就已经发出。

所以流式接口出错时的通用做法是：

```python
yield f"data: {json.dumps({'type': 'error', 'message': '...'}, ensure_ascii=False)}\n\n"
```

在流内发一个 error 事件，客户端解析到这个类型就知道出错了，然后正常结束流。

反过来，如果错误发生在**开始推流之前**（比如 Pydantic 校验失败），此时状态码还没发，返回 422 或 500 完全没问题。

### 3.9 响应头里的证据

`/docs` 测试后查看 Response headers：

```
content-type: text/event-stream; charset=utf-8
transfer-encoding: chunked
```

- `text/event-stream` —— `media_type` 参数生效了
- `chunked` —— 分块传输。普通响应会在头里写 `content-length` 告诉客户端总字节数，但流式响应开始发送时还不知道总长度，所以改用分块传输。**这恰好印证了「头部在第一块数据之前就发出」这个结论。**

---

## 第四章 Docker

### 4.1 它解决什么问题

服务能在自己电脑上跑，靠的是一连串恰好成立的条件：特定的 Python 版本、装好依赖的虚拟环境、正确的目录结构、知道在哪个目录执行哪条命令。换一台机器，这些条件可能一个都不满足——这就是「在我电脑上明明能跑」问题。

Docker 的思路：**把程序和它运行所需的一切打包在一起**，包括操作系统基础文件、Python 解释器、所有依赖、代码和启动命令。

### 4.2 三个核心概念

| 概念 | 是什么 | 类比 |
|---|---|---|
| **镜像 Image** | 打包好的只读安装包 | 系统安装光盘 / Python 的类 |
| **容器 Container** | 用镜像启动的运行实例 | 装好并开机的电脑 / 类的对象 |
| **Dockerfile** | 描述如何构建镜像的文本文件 | 菜谱 |

关系：**Dockerfile →（build）→ 镜像 →（run）→ 容器**

**镜像不是对你电脑的「拍照备份」**，而是按 Dockerfile 从零构建出来的。正因为不依赖宿主机状态，别的机器才能得到一模一样的结果。

**一个镜像可以启动多个容器。** 实测验证：运行两次 `docker run hello-world` 后，`docker images` 只有 1 个镜像，`docker ps -a` 有 2 个容器。

### 4.3 客户端与守护进程

`docker run hello-world` 的输出里藏着一个重要信息：

```
1. The Docker client contacted the Docker daemon.
2. The Docker daemon pulled the "hello-world" image from the Docker Hub.
3. The Docker daemon created a new container from that image...
```

你在终端敲的 `docker` 命令只是**客户端**，它把指令发给后台常驻的**守护进程（daemon）**，真正拉镜像、建容器的是守护进程。Docker Desktop 左下角的 `Engine running` 指的就是它。

**这和第三章写的客户端/服务端是同一种架构。** 所以当终端报「无法连接到守护进程」时，第一反应应该是检查 Docker Desktop 是否在运行。

### 4.4 完整的 Dockerfile

```dockerfile
# 基础镜像：已装好 Python 3.11 的精简版 Linux
# 版本号要写具体的，不要用 latest，否则今天和明天构建出的环境可能不同
FROM python:3.11-slim

# 设置工作目录，此后所有指令都在这里执行，相当于 cd /app
# 目录不存在会自动创建
WORKDIR /app

# 先单独复制依赖清单，. 表示当前工作目录也就是 /app
COPY requirements.txt .

# 构建时执行安装，结果会被固化进镜像
# --no-cache-dir 不保留 pip 下载缓存，让镜像更小
RUN pip install -r requirements.txt --no-cache-dir

# 再复制代码，保留 week3 文件夹结构，结果是 /app/week3/main.py
COPY week3 ./week3

# 声明容器使用的端口，仅为说明性标注，实际生效的是 run 时的 -p 参数
EXPOSE 8000

# 容器启动时执行的命令，列表形式，每个部分单独一个字符串
CMD ["uvicorn", "week3.main:app", "--host", "0.0.0.0"]
```

### 4.5 指令速查

| 指令 | 执行时机 | 作用 |
|---|---|---|
| `FROM` | 构建 | 指定基础镜像，必须是第一条 |
| `WORKDIR` | 构建 | 设置工作目录 |
| `COPY 来源 目标` | 构建 | 从宿主机复制文件进镜像 |
| `RUN` | **构建时** | 执行命令，结果固化进镜像 |
| `EXPOSE` | 元数据 | 声明端口，说明性质 |
| `CMD` | **容器启动时** | 声明启动命令 |

**`RUN` 和 `CMD` 的区别必须分清**：装依赖用 `RUN`（构建时跑一次），启动服务用 `CMD`（每次启动容器时跑）。

### 4.6 分层缓存决定了指令顺序

Dockerfile 每一步生成一「层」，Docker 会缓存每一层。重新构建时，若某层及其之前的步骤都没变，直接用缓存。

**关键规则：一旦某层的输入变了，这一层和它下面的所有层都要重新执行。**

实测数据（首次构建）：

| 步骤 | 耗时 |
|---|---|
| `RUN pip install` | 31.5 秒 |
| `COPY week3 ./week3` | 0.1 秒 |

所以必须**先复制 requirements.txt 并安装依赖，最后才复制代码**：

- 正确顺序：改一行代码 → 只有最后一层失效 → 几秒构建完
- 错误顺序：改一行代码 → 复制代码层失效 → 安装依赖层跟着失效 → **依赖没变也要重装一遍**

### 4.7 容器网络与 `--host 0.0.0.0`

**这是把 FastAPI 部署进 Docker 最常踩的坑，没有之一。**

一台机器上通常有多个网络接口：

- **回环接口**（loopback，`127.0.0.1`）：只在机器内部转圈，不经过任何网卡
- **对外接口**：连接外部网络

容器是一台独立的「小电脑」，有自己的回环接口，也有一个连到 Docker 虚拟网络的接口（地址类似 `172.17.0.2`）。**外部请求经过端口映射后，是从虚拟网络接口进入容器的，而不是从回环接口。**

uvicorn 默认监听 `127.0.0.1`，意思是「只理会从回环接口来的连接」，所以外面转发进来的请求会被拒绝。

解决办法是监听 `0.0.0.0`，含义是「**所有网络接口的连接都接受**」。

端口映射：

```bash
-p 9000:8000    # 格式是 本机端口:容器端口
```

浏览器访问本机 9000，请求被转发到容器的 8000。

### 4.8 `.dockerignore`

放在**项目根目录**，与 Dockerfile 同级。因为它管的是「构建上下文」，也就是 `docker build` 末尾那个 `.` 所指的目录。

```
.venv
.git
.idea
__pycache__
*.pyc
.env
```

两个价值：

1. `.venv` 可能几百 MB，传进去纯属浪费
2. **`.env` 里有密钥，绝对不能打包进镜像**

它和 `.gitignore` 作用相似但不完全相同：`.dockerignore` 通常额外排除 `.git`（几十 MB 版本历史，容器里用不上）。

### 4.9 常用命令

```bash
# 构建镜像，-t 起名字，冒号后是标签（版本），末尾的 . 指定构建上下文
docker build -t ai-agent-learning:week3 .

# 运行容器，-d 后台运行，-p 端口映射，--name 指定名字
docker run -d -p 8000:8000 --name week3-api ai-agent-learning:week3

# 查看正在运行的容器
docker ps

# 查看所有容器（含已停止）
docker ps -a

# 查看容器日志
docker logs week3-api
docker logs --tail 20 week3-api      # 只看最近 20 行
docker logs -f week3-api             # 持续跟踪，Ctrl+C 退出
docker logs week3-api | grep ERROR   # 配合管道筛选

# 进入运行中的容器，-it 交互式，bash 打开一个 shell
docker exec -it week3-api bash

# 查看容器内进程（不依赖容器里装了什么）
docker top week3-api

# 停止 / 启动 / 删除
docker stop week3-api
docker start week3-api               # 启动已存在的容器，不会新建
docker rm week3-api
```

### 4.10 `run` 和 `start` 的区别

| 命令 | 行为 |
|---|---|
| `docker run` | **新建** + 启动，每执行一次多一个容器 |
| `docker start` | 启动**已存在**的容器 |

不知道这个区别的话，反复用 `run` 调试服务，几天下来会攒出几十个停止的容器占着磁盘。

**按「会不会改变状态」给命令分类：**

- 只看不改（随便执行）：`docker ps`、`docker images`、`docker logs`、`docker top`
- 会改变状态（执行前想清楚）：`docker run`、`docker rm`、`docker rmi`、`docker build`

### 4.11 容器的生命周期由主进程决定

对比两次实验：

| 镜像 | STATUS | 原因 |
|---|---|---|
| `hello-world` | `Exited (0)` | 打印完文字就没事做了 |
| 自建 FastAPI 镜像 | `Up 12 seconds` | uvicorn 一直运行监听 |

日志里的 `Started server process [1]` 揭示了本质：在 Linux 里 1 号进程是系统启动的第一个进程，**在容器里 uvicorn 就是「头号进程」，它一结束容器就停止**。

`Exited (0)` 括号里是退出码，0 表示正常结束，非 0 表示出错。排查容器启动失败时，退出码是重要线索。

### 4.12 容器里的修改不会保存

进容器后看到提示 `A new release of pip is available`，**不需要更新，更新了也没意义**。

容器是临时的，任何手工修改只存在于这个实例中。执行 `docker rm` 或重新 `docker build` 后，改动就消失了。

**Docker 的设计哲学：镜像是唯一的事实来源。** 想让容器环境有变化，正确做法是改 Dockerfile 然后重新构建，而不是进容器手动操作。

> 实际工作中新手常犯的错误是「服务出问题了，进容器改个配置先跑起来」，结果容器一重启改动全没，问题又复现。

---

## 第五章 Linux 命令行

### 5.1 文件系统结构

Windows 有 C 盘、D 盘多个根；Linux **只有一个根 `/`**，所有东西都挂在它下面。

| 路径 | 用途 |
|---|---|
| `/home/用户名` | 主目录，可简写为 `~` |
| `/etc` | 系统和软件的配置文件 |
| `/var/log` | 日志文件，排查线上问题必去 |
| `/usr/bin` | 大部分命令程序本体 |
| `/app` | 非系统自带，是 Dockerfile 里 `WORKDIR` 创建的 |

`.` 表示当前目录，`..` 表示上一级目录。PowerShell 里的 `cd ..` 就是从 Linux 借来的。

### 5.2 命令格式

```
命令 [选项] [参数]
```

- **选项**调整行为：短选项一个横杠加单字母（`-l`），长选项两个横杠加单词（`--help`），多个短选项可合并（`-la` = `-l -a`）
- **参数**是操作对象，通常是文件或目录

`docker ps -a`、`uvicorn main:app --reload` 都是这个格式。

### 5.3 常用命令速查

**定位与浏览**

| 命令 | 作用 |
|---|---|
| `pwd` | 打印当前目录 |
| `ls` | 列出目录内容 |
| `ls -l` | 详细列表（权限、大小、时间） |
| `ls -a` | 显示隐藏文件（以点开头的） |
| `cd 路径` | 切换目录 |
| `cd ~` / `cd`（不带参数） | 回主目录 |
| `cd -` | 回上一次所在的目录 |

**查看文件**

| 命令 | 作用 |
|---|---|
| `cat 文件` | 一次性输出全部，适合短文件 |
| `less 文件` | 分页查看，`q` 退出 |
| `head -n 20 文件` | 看**开头** 20 行 |
| `tail -n 20 文件` | 看**末尾** 20 行 |
| `tail -f 文件` | 持续跟踪末尾，日志实时刷新 |

> **日志排查几乎只用 `tail`**，因为你关心的永远是「刚刚发生了什么」，而日志是往后追加的。

**增删改**

| 命令 | 作用 |
|---|---|
| `mkdir 目录名` | 新建目录 |
| `touch 文件名` | 新建空文件 |
| `cp 来源 目标` | 复制（目录加 `-r`） |
| `mv 来源 目标` | 移动 / 重命名 |
| `rm 文件` | 删除文件 |
| `rm -r 目录` | 递归删除目录及内容 |

**查找与过滤**

| 命令 | 作用 |
|---|---|
| `grep 关键词 文件` | 搜索包含关键词的行 |
| `find 路径 -name "名字"` | 按名字查找 |
| `\|`（管道） | 把前一个命令的输出交给后一个处理 |

**其他**

| 命令 | 作用 |
|---|---|
| `ps aux` | 查看所有进程 |
| `kill 进程号` | 结束进程 |
| `sudo 命令` | 以管理员权限执行 |
| `chmod +x 文件` | 加可执行权限 |
| `Tab` | 自动补全，强烈建议养成习惯 |
| `↑` `↓` | 翻历史命令 |

### 5.4 `rm` 的危险性

**`rm` 没有回收站，删了就没了，而且不会询问确认。**

注意 `rm` 不是「只能删文件」，而是**默认不递归**：对目录执行会报错拒绝，加 `-r` 才会连内容一起删。

`rm -rf /` 会毁掉整个系统。网上有很多拿它开玩笑的段子，但在真实服务器上执行就是生产事故。

> **养成习惯：执行 `rm` 前先 `pwd` 确认自己在哪，再 `ls` 确认要删的是什么。**

### 5.5 读懂 `ls -l` 的输出

```
-rw-r--r-- 1 ruiwen ruiwen 12 Sep 23 11:03 linux-notes.txt
```

| 部分 | 含义 |
|---|---|
| `-` | 类型：`-` 普通文件，`d` 目录 |
| `rw-r--r--` | 权限，三组各三位：**所有者 / 所属组 / 其他人**，`r` 读 `w` 写 `x` 执行 |
| `1` | 硬链接数 |
| `ruiwen ruiwen` | 所有者 / 所属组 |
| `12` | 文件大小（字节） |
| `Sep 23 11:03` | 最后修改时间 |
| `linux-notes.txt` | 文件名 |

上例中：所有者可读可写，其他人只能读。`chmod +x` 加的就是那个 `x`——shell 脚本必须有 `x` 权限才能直接运行。

### 5.6 进容器排查：本节的实战价值

```bash
docker exec -it week3-api bash
```

进入后提示符变成 `root@6351520bf2f3:/app#`。注意结尾是 `#` 而不是 `$`——在 Linux 里 `#` 表示 root（管理员），`$` 表示普通用户。

验证 Dockerfile 效果的一套动作：

```bash
pwd                      # 验证 WORKDIR /app 生效
ls                       # 应看到 requirements.txt 和 week3
ls week3                 # 确认 main.py 在里面，验证 COPY 生效
cat requirements.txt     # 确认依赖清单内容
pip list                 # 看容器里实际装了哪些包
cat /proc/1/cmdline      # 看 1 号进程的启动命令
exit                     # 退出容器
```

**这套动作是排查线上问题最基础也最常用的手段**：确认文件是否到位、依赖是否装对、进程是否正常。

### 5.7 三个终端必须分清

本周开始同时存在多个环境，混用会直接报错：

| 提示符 | 所在环境 | 能用什么 |
|---|---|---|
| `PS D:\...>` | Windows（PyCharm 终端） | docker、git、python、uvicorn |
| `ruiwen@主机名:~$` | WSL 里的 Ubuntu | Linux 命令 |
| `root@容器ID:/app#` | Docker 容器内部 | 容器里装了的东西 |

还要和 Python 交互环境区分开：

| 提示符特征 | 是什么 | 输入什么 |
|---|---|---|
| 有路径和 `>` | 系统终端 | 命令 |
| `>>>` | Python REPL | Python 代码 |
| 无提示符，只滚输出 | 运行窗口 | 不接受输入 |

---

## 第六章 典型错误合集

> ⚠️ **本章所有标记 ❌ 的代码都是错误示范，请勿复制使用。**
> 按根因分类而非时间顺序，因为归类后能看出反复犯错的模式。

### 根因一：路径与环境的一致性（本周最大的坑，共 4 次）

这是贯穿本周的主线问题：uvicorn 的导入路径、Dockerfile 的 COPY 与 CMD、Linux 的当前目录，本质上都是同一件事——**「从哪个起点出发去找东西」必须前后一致**。

---

**错误 1：在项目根目录启动 week3 里的服务**

```bash
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
PS D:\PythonProjects\ai-agent-learning> uvicorn main:app --reload
```

报错：

```
ERROR:    Error loading ASGI app. Could not import module "main".
```

**原因**：`main:app` 是相对于终端当前目录解析的。根目录下没有 `main.py`，它在 `week3/` 里面。

---

**错误 2：进入 week3 后启动，但代码里用的是绝对导入**

```bash
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
PS D:\PythonProjects\ai-agent-learning\week3> uvicorn main:app --reload
```

报错（traceback 最后两行）：

```
File "D:\PythonProjects\ai-agent-learning\week3\main.py", line 6, in <module>
    from week3.models import ChatRequest
ModuleNotFoundError: No module named 'week3'
```

**原因**：已经在 `week3` 文件夹**里面**了，当前目录下没有另一个 `week3` 文件夹。

**✅ 正确做法**：

```bash
PS D:\PythonProjects\ai-agent-learning> uvicorn week3.main:app --reload
```

**规律总结表**：

| 终端位置 | 启动命令 | 代码里的导入 | 结果 |
|---|---|---|---|
| 根目录 | `uvicorn main:app` | — | ❌ 找不到 main.py |
| week3 里 | `uvicorn main:app` | `from week3.models` | ❌ 找不到 week3 |
| 根目录 | `uvicorn week3.main:app` | `from week3.models` | ✅ 两边一致 |

**核心原则：启动命令的写法和代码里导入的写法，必须基于同一个「起点目录」。**

---

**错误 3：在上一级目录操作下级目录的文件**

```bash
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
ruiwen@host:~$ mv notes.txt linux-notes.txt
mv: cannot stat 'notes.txt': No such file or directory
```

**原因**：`notes.txt` 在 `linux-practice/` 里面，而当前在它的上一级。**Linux 命令默认只在当前目录下找文件。**

**✅ 正确做法**：先 `cd linux-practice` 再执行，或者写完整路径。

---

**错误 4：Dockerfile 里 COPY 位置与 CMD 模块路径不匹配**

```dockerfile
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
WORKDIR /app
COPY week3 /              # ← 复制到了容器根目录，不是 /app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0"]   # ← 模块路径也对不上
```

**✅ 正确做法**：

```dockerfile
WORKDIR /app
COPY week3 ./week3        # 结果是 /app/week3/main.py
CMD ["uvicorn", "week3.main:app", "--host", "0.0.0.0"]
```

两种 COPY 方式的区别：

| 写法 | 容器内结构 | 对应的模块路径 |
|---|---|---|
| `COPY week3 .` | `/app/main.py` | `main:app` |
| `COPY week3 ./week3` | `/app/week3/main.py` | `week3.main:app` |

选后者还有一个原因：代码里写的是 `from week3.models import ChatRequest`，必须从 `/app` 出发才能成立。

---

### 根因二：数据结构与执行顺序

**错误 5：算出了 JSON 却没有 yield 出去**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
async def generate_json_text(content):
    data = {"role": "zrw", "content": "这个问题有些复杂"}
    text = json.dumps(data, ensure_ascii=False)   # ← 算完了，但从没发出去
    yield "data: [DONE]\n\n"                      # ← 只发了结束信号
```

**现象**：客户端只收到一行 `data: [DONE]`，没有任何正文。

**原因**：`text` 变量算完就被丢弃了，PyCharm 里它显示为灰色（未使用）就是提示。

**✅ 正确做法**：在循环里逐字构造并 `yield`，见 3.5 节完整代码。

---

**错误 6：先转 JSON 再逐字循环（顺序颠倒）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
text = json.dumps(data, ensure_ascii=False)   # 整句话先转成 JSON 字符串
for char in text:                             # ← 对 JSON 字符串逐字符循环
    yield f"data: {char}\n\n"
```

**现象**：客户端收到的是：

```
data: {

data: "

data: t
```

**原因**：`json.dumps` 的结果是一个字符串，对它逐字循环拆出来的是 `{`、`"`、`t`、`y`、`p`…… 每一块都不是完整 JSON。

**✅ 正确顺序**：先对回复逐字循环，**每拿到一个字，再把这一个字包成 JSON**。

---

**错误 7：循环变量在循环结束后仍保留最后一轮的值**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
for char in reply:
    data = {"type": "delta", "content": char}
    text = json.dumps(data, ensure_ascii=False)
    yield f"data: {text}\n\n"
    await asyncio.sleep(0.5)

yield f"data: {usage_json}\n\n"
yield f"data: {text}\n\n"        # ← 多余的一行，text 还保留着最后一个字
yield "data: [DONE]\n\n"
```

**现象**：客户端拼出来的回复末尾多了一个字（「我正在思考考」），而且 delta 出现在 usage 之后，违反了事件顺序约定。

**原因**：`text` 在每轮循环被重新赋值，循环结束后保留的是最后一轮的值。

PyCharm 会在这一行给出黄色警告「`text` 可能在赋值之前被引用」——因为如果 `reply` 是空字符串，循环一次都不执行，`text` 从未定义，会抛 `NameError`。

**✅ 正确做法**：删掉这一行。

---

**错误 8：计数器写在循环外面**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
for char in reply:
    yield f"data: {text}\n\n"
completion_tokens += 1      # ← 缩进在循环外，只会加一次
```

**✅ 正确做法**：计数器 `+= 1` 必须在循环**内部**，缩进与 `yield` 对齐。

> 关于计数位置的一个细节：放在 `yield` **之后**统计的是「真正发出去的字数」，放在之前则最后一个字即使没发出也会被计入（客户端中途断开时会有差异）。真实计费一般按实际生成量算，两种写法都说得通。

---

### 根因三：协议与格式约束

**错误 9：给 SSE 的 JSON 加 indent**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
text = json.dumps(data, ensure_ascii=False, indent=2)
```

**原因**：产生多行 JSON，而 SSE 按行解析，只有 `data:` 开头的行才算数据。客户端只拿到 `{`，`json.loads` 报错。

**✅ 正确做法**：不传 `indent`。

> 补充：SSE 协议其实允许一个事件写多行 `data:`，接收端会用换行拼接。但那要求每行都带 `data:` 前缀，`json.dumps` 不会帮你加，所以实践中一律坚持单行。

---

**错误 10：对 `[DONE]` 直接调用 `json.loads`**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
for line in response.iter_lines():
    data = json.loads(line.replace("data: ", ""))   # 遇到 [DONE] 直接抛异常
```

**✅ 正确做法**：先判断再解析。

```python
payload = line.replace("data: ", "")
if payload == "[DONE]":
    break
data = json.loads(payload)
```

---

**错误 11：CMD 把整条命令挤在一个字符串里**

```dockerfile
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
CMD ["uvicorn main:app --reload"]
```

**原因**：Docker 会把整个字符串当成一个可执行文件名去找，结果找不到名为 `uvicorn main:app --reload` 的程序。

**✅ 正确做法**：每个部分单独一个字符串。

```dockerfile
CMD ["uvicorn", "week3.main:app", "--host", "0.0.0.0"]
```

顺带两点：`--reload` 要去掉（容器里代码固定不变，留着浪费资源）；`--host` 和 `0.0.0.0` 是两个独立的字符串，不能写成一个。

---

**错误 12：COPY 的目标路径与文件名粘连**

```dockerfile
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
COPY requirements.txt .requirements
COPY week3./week3 .week3
```

**原因**：`.` 是一个独立的路径（表示当前工作目录），不是前缀。`.requirements` 会被理解成一个叫这个名字的隐藏文件。

**✅ 正确做法**：`COPY 来源 目标`，中间一个空格，正好两个部分。

```dockerfile
COPY requirements.txt .
COPY week3 ./week3
```

---

### 根因四：环境隔离（容器/WSL/宿主机是三套独立环境）

**错误 13：requirements.txt 漏了 uvicorn**

```
docker: Error response from daemon: failed to create task for container:
... exec: "uvicorn": executable file not found in $PATH
```

**原因**：本机 `.venv` 里手动装过 uvicorn，但没写进 `requirements.txt`。**容器是从零构建的，不会继承宿主机的任何东西，清单里没写的容器里就没有。**

**✅ 正确做法**：`pip list` 对照检查，补全清单；或用 `pip freeze > requirements.txt` 自动生成。

> 这个容器**创建成功了但启动失败**，名字被占用，必须 `docker rm week3-api` 后才能重新 run。

---

**错误 14：在 WSL Ubuntu 里执行 docker 命令**

```
ruiwen@host:~$ docker ps
The command 'docker' could not be found in this WSL 2 distro.
```

**原因**：Docker Desktop 装在 Windows 上，`docker` 命令注册在 Windows 的 PATH 里。Ubuntu 是独立环境，有自己的 PATH，默认看不到 Windows 的命令。

**✅ 正确做法**：在 PowerShell 里执行；或在 Docker Desktop 的 Settings → Resources → WSL Integration 里打开对应发行版的开关。

---

**错误 15：在 slim 镜像里执行 `ps aux`**

```
root@6351520bf2f3:/app# ps aux
bash: ps: command not found
```

**原因**：`python:3.11-slim` 只保留运行 Python 必需的东西，`ps`、`vim`、`curl` 这些系统工具都被砍掉了，换来的是更小的镜像体积。

**✅ 替代方案**：

```bash
docker top week3-api      # 从容器外面看，由 Docker 提供，不依赖容器内容
cat /proc/1/cmdline       # 在容器里读 /proc，Linux 把进程信息以文件形式暴露在这里
```

> 实际工作中会遇到同样的情况：进到线上容器想排查问题，发现连 `ps` 都没有。

---

### 根因五：调用与语法细节

**错误 16：定义了参数但调用时没传实参**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
async def generate_json_text(content):      # 定义时声明需要一个 content
    ...

@app.post("/chat/stream")
async def chat_stream(receive: ChatRequest):
    return StreamingResponse(
        generate_json_text(),               # ← 括号是空的，参数没传
        media_type="text/event-stream",
    )
```

**识别信号**：PyCharm 里 `receive` 显示为**灰色**（定义了但未使用），调用处有**黄色波浪线**。

**✅ 正确做法**：`generate_json_text(receive.content)`。改完后 `receive` 会变亮——这是个很好的自检信号。

---

**错误 17：`mv` 的参数顺序写反**

```bash
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
mv linux-notes.txt notes.txt     # 想把 notes.txt 改名，却把它写在了后面
```

**✅ 正确做法**：`mv 来源 目标`，来源在前。

```bash
mv notes.txt linux-notes.txt
```

**规律：Linux 世界里几乎所有「从 A 到 B」的命令都是来源在前**——`cp`、`mv`，包括 Dockerfile 的 `COPY`。

---

**错误 18：`ls` 打成数字 `1s`**

```bash
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
1s -l
1s: command not found
```

**原因**：终端等宽字体里 `1`（一）、`l`（L 小写）、`I`（i 大写）长得很像。本周犯了两次。

**✅ 预防办法**：用 **Tab 补全**。输入 `l` 按 Tab，能补全就说明打对了。命令敲不对时，先怀疑是不是这类字符混淆。

---

**错误 19：FastAPI 重复路由静默覆盖**

同一个路径注册了两个处理函数时，**FastAPI 不报错，只使用第一个**。代码看着对但实际没生效，且没有任何提示。

**✅ 排查办法**：打开 `/docs` 查看接口实际的请求体结构。如果和源码不符，说明加载的是另一个版本。

---

### 错误统计

| 根因分类 | 次数 |
|---|---|
| 路径与环境的一致性 | 4 |
| 数据结构与执行顺序 | 4 |
| 协议与格式约束 | 4 |
| 环境隔离 | 3 |
| 调用与语法细节 | 4 |

**最值得记住的一条**：本周近三分之一的错误，根源都是「**起点目录不一致**」。uvicorn 的模块路径、Dockerfile 的 COPY 与 CMD、Linux 的相对路径，考察的是同一种思维——**先确认「我现在在哪」，再决定「路径怎么写」**。

---

## 第七章 环境搭建踩坑记录

国内网络环境下安装开发工具的经验，单独记一章，以后配置服务器会反复用到。

### 7.1 `wsl --install` 下载失败

```
正在下载: 适用于 Linux 的 Windows 子系统 2.7.14
服务器返回无效或不可识别的响应
```

**原因**：WSL 安装包托管在 GitHub 上，国内访问不稳定，速度可能降到 0 B/s 并最终中断。

**解决路线**（按优先级）：

1. 手动开启两个 Windows 功能（本地操作，不需要联网）：

```powershell
# /online 对当前运行的系统操作，/all 连同依赖一起开启，/norestart 先不重启
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

2. 从 **Microsoft Store** 安装 `Windows Subsystem for Linux`（微软商店有国内 CDN，比 GitHub 快得多）
3. 同样从商店安装 `Ubuntu`
4. 验证：`wsl -l -v`，VERSION 列应显示 `2`

### 7.2 安全提醒

搜索「Docker Desktop 下载慢」会看到网盘链接或非官方站点提供的安装包。**不要使用**。安装包会以管理员权限运行，来路不明的文件有被篡改的风险。只从官网或知名高校、大厂镜像站下载。

可以验证签名：右键安装包 → 属性 → 数字签名，签名者应为 `Docker Inc`。

### 7.3 终端 PATH 不会自动刷新

装完 Docker 后，已经打开的 PyCharm 终端仍然找不到 `docker` 命令。

**原因**：终端启动时读取一次系统 PATH，之后安装的软件不会自动同步。

**解决**：完全关闭 PyCharm 再重新打开。以后装任何命令行工具都会遇到这个现象。

---

## 第八章 本周自检

- [x] 能解释 FastAPI 和 uvicorn 各自的职责
- [x] 能用 Pydantic 定义模型，并说明校验失败时会发生什么
- [x] 能说清 `yield` 和 `return` 的区别，以及为什么流式必须用生成器
- [x] 能写出符合 SSE 规范的数据块（`data: ` 前缀 + `\n\n` 结尾 + 单行 JSON）
- [x] 知道 usage 统计块为什么只能放在流的最后
- [x] 知道流式接口开始推送后为什么不能再改状态码
- [x] 能说明镜像和容器的区别，以及一个镜像能启动几个容器
- [x] 能独立写出一个可运行的 Dockerfile
- [x] 知道为什么必须 `--host 0.0.0.0`
- [x] 知道为什么要先 COPY requirements.txt 再 COPY 代码
- [x] 能用 `docker exec` 进容器排查问题
- [x] 能区分 PowerShell / WSL Ubuntu / 容器内部三种终端

---

## 附录 A：本周完整命令速查

```bash
# ---------- 服务启动 ----------
uvicorn week3.main:app --reload              # 开发环境，自动重载
uvicorn week3.main:app --host 0.0.0.0        # 容器内，监听所有接口

# ---------- Docker 镜像 ----------
docker build -t ai-agent-learning:week3 .    # 构建，末尾的 . 不能少
docker images                                # 列出本地镜像
docker rmi 镜像名                             # 删除镜像

# ---------- Docker 容器 ----------
docker run -d -p 8000:8000 --name week3-api ai-agent-learning:week3
docker ps                                    # 运行中的容器
docker ps -a                                 # 所有容器
docker logs -f week3-api                     # 持续跟踪日志
docker exec -it week3-api bash               # 进入容器
docker top week3-api                         # 查看容器内进程
docker stop / start / rm week3-api           # 停止 / 启动 / 删除

# ---------- Linux 基础 ----------
pwd                                          # 我在哪
ls -la                                       # 看有什么（含隐藏文件）
cd ~ / cd .. / cd -                          # 主目录 / 上级 / 上一次的目录
cat / less / head -n 20 / tail -n 20         # 看文件
tail -f app.log                              # 盯日志
cat app.log | grep ERROR                     # 管道筛选
mkdir / touch / cp -r / mv / rm -r           # 增删改

# ---------- Git ----------
git status                                   # 提交前先看这个
git add .
git commit -m "week3: ..."
git push origin main
```

## 附录 B：提交记录

本周的提交节奏遵循「一个功能完成就 commit，commit 完立即 push」：

```
week3: SSE task4 JSON stream
week3: SSE task5 usage chunk
week3: add Dockerfile for FastAPI service
```

**为什么不攒着一次性提交**：

1. **防丢** —— commit 只存在本地，硬盘坏了就没了
2. **冲突更容易处理** —— 多人协作时，攒一周不推送很可能和别人撞车
3. **提交记录更有价值** —— 公开仓库的连续提交历史，比一次性大提交更能说明学习的持续性

---

## 下周预告

第 4 周：裸调 LLM API 与 Prompt 工程。不用任何 SDK 封装，用 httpx 直接 POST 到 `/v1/chat/completions`，把本周写的 mock 回复换成真正的大模型流式输出。

本周留下的两个加分项，届时可以一并补上：

- usage 块里加 `elapsed_ms`（总耗时）和 `ttft_ms`（首 token 延迟）
- 用 httpx 写流式客户端，把 delta 拼接成完整回复

其中 **TTFT（time to first token）是大模型应用最重要的性能指标之一**，直接决定用户「感觉快不快」。
