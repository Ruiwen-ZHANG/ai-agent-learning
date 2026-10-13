# 第 4 周技术总结：裸调 LLM API 与 Prompt 工程

> 16 周 AI Agent 应用开发学习记录 · 第 4 周
> 关键词：DeepSeek API、Token 与计费、流式输出、多轮对话、Prompt 工程、JSON Mode

---

## 本周概览

前三周一直在打地基：Python 工程、HTTP、FastAPI、Docker。这周第一次真正**接触大模型**。

视角也变了。第 2 周我是 HTTP 客户端，第 3 周是服务端，这周**同时是两者**：

```
用户 → 我的服务 → 大模型 API
     ←          ←
```

对用户来说我是服务端，对大模型来说我是客户端。第 3 周写的那个 mock SSE 服务，这周学会了怎么把 mock 换成真正的转发。

| 小节 | 内容 | 产出文件 |
|---|---|---|
| 1 | 请求结构与第一次调用 | `first_call.py` |
| 2 | Token 与计费 | `cost_tracker.py` |
| 3 | 流式输出 | `stream_call.py` |
| 4 | 多轮对话与上下文窗口 | `multi_turn.py` |
| 5 | Prompt 工程与 JSON Mode | `extract.py` |

**本周核心原则：不用任何 SDK，全部裸调。** SDK 把细节藏起来了，出问题时不知道该查什么。见过原始请求体和响应体之后，以后无论用哪个框架，遇到报错都能判断是自己传错了参数还是服务端的问题。

**代码仓库**：`https://github.com/Ruiwen-ZHANG/ai-agent-learning`

---

## 第零章 一个重要教训：文档才是唯一可靠来源

学习路线文档里写的模型名是 `deepseek-chat`。实际查官方文档才发现，**这个模型名已经在 2026 年 7 月 24 日下线了**。

当前可用的是：

| 模型名 | 对应版本 | 特点 |
|---|---|---|
| `deepseek-flash` | DeepSeek-V4.1-Flash | 便宜、快、支持多模态 |
| `deepseek-v4-pro` | DeepSeek-V4-Pro-0813 | 能力更强，价格约 4 倍 |

base URL：`https://api.deepseek.com`，上下文长度 1M。

**教训**：大模型领域迭代极快，任何教程里的模型名、参数、价格都可能在几个月内失效。**查官方文档，而不是博客或教程。** 本周后面还有一次类似经历——思考模式的参数名也是靠查文档才确定的。

---

## 第一章 请求结构与第一次调用

### 1.1 一次调用就是一个 POST 请求

```
POST https://api.deepseek.com/v1/chat/completions
```

和第 2 周学的 HTTP 结构完全对应：

**请求头**

```python
headers = {
    "Content-Type": "application/json",      # 告诉服务器请求体是 JSON
    "Authorization": f"Bearer {key}",        # 身份认证，Bearer 后面有一个空格
}
```

`Bearer` 是认证方案的名称，意思是「持有此令牌者即可访问」。格式写错会返回 401。

> **注意**：`json=payload` 参数会让 httpx 自动设置 Content-Type，所以第一个头其实可以省略。显式写出来是为了看清一个完整请求的样子。

**请求体核心字段**

| 字段 | 类型 | 作用 |
|---|---|---|
| `model` | 字符串 | 用哪个模型 |
| `messages` | 数组 | 对话内容，**最重要的字段** |
| `temperature` | 数字 | 输出随机性，0 到 2 |
| `max_tokens` | 整数 | 最多生成多少 token |
| `stream` | 布尔 | 是否流式返回 |
| `thinking` | 对象 | 思考模式开关 |
| `response_format` | 对象 | 输出格式约束 |

### 1.2 messages 是数组，不是单条消息

```python
"messages": [
    {"role": "system", "content": "你是一个简洁的助手，回答不超过50字"},
    {"role": "user", "content": "什么是SSE"},
]
```

三种 role：

| role | 谁说的 | 用途 |
|---|---|---|
| `system` | 开发者 | 设定身份、风格、规则，整轮对话都生效 |
| `user` | 用户 | 用户的提问 |
| `assistant` | 模型 | 模型之前的回复，多轮对话时要带上 |

**system 和 user 的区别**：system 是「你是谁、你该怎么做」，user 是「我要问什么」。system 写一次管全程，是控制模型行为的主要手段。

> 这个结构第 3 周见过——当时自己定义的 `ChatRequest` 就是 `role` + `content`，是模仿这个格式写的。

### 1.3 temperature 控制的是随机性，不是「精细度」

模型每一步预测下一个词时，会得到一个概率分布。temperature 调的是从这个分布里怎么挑：

- **0** —— 永远挑概率最高的，**同样输入基本得到同样输出**
- **1** —— 默认值，有一定随机性
- **1.5 以上** —— 可能语无伦次

**抽取、分类、代码生成这类任务设 0，真正的理由是「需要结果稳定可复现」，而不是「更准确」。** 温度高不会让模型变笨，只会让它每次说得不一样——对于要解析成 JSON 的输出，不稳定就是灾难。

**实测**：`temperature=0.7` 下同一个问题问两次，一次答「允许服务器单向实时向浏览器推送数据」，一次答「常用于消息通知、股票行情等场景」。

### 1.4 响应结构

```json
{
  "id": "6b3f3e82-b72f-40d9-94e7-3ac01f8a8af3",
  "object": "chat.completion",
  "model": "deepseek-flash",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "SSE指服务器发送事件……" },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 18,
    "completion_tokens": 21,
    "total_tokens": 39,
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": 18
  }
}
```

**取内容的完整路径**：

```python
data = response.json()                                   # 先转成 Python 字典
content = data["choices"][0]["message"]["content"]
```

**`choices` 是数组**，因为 API 支持一次生成多个候选（通过 `n` 参数），默认只有一个，所以取 `[0]`。

**`usage` 眼熟吗？** 这就是第 3 周自己 mock 出来的那个统计块，字段名完全一样。当时是编的，现在是真的。

**`finish_reason`** —— 为什么停下来：

| 值 | 含义 | 处理 |
|---|---|---|
| `stop` | 正常说完 | 无 |
| `length` | 撞到 `max_tokens` 被截断 | 提高上限或压缩输出 |
| `tool_calls` | 模型要调工具 | 第 5 周内容 |

回复不完整时，先看它是不是 `length`。

### 1.5 三层防护：超时、异常、状态码

真实网络调用，**失败是常态而不是例外**。

**第一层：超时**

```python
response = httpx.post(url, headers=headers, json=payload, timeout=30)
```

不加的话，服务器卡住时程序会无限等待，既不报错也不结束。

**第二层：异常捕获**

```python
try:
    response = httpx.post(...)
except httpx.TimeoutException as e:      # 超时
    print("超时了:", e)
    sys.exit(1)
except httpx.RequestError as e:          # 网络层问题（连不上、DNS 失败）
    print("网络错误:", e)
    sys.exit(1)
```

**顺序有讲究**：`TimeoutException` 必须写在 `RequestError` 前面。超时在 httpx 里属于网络错误的子类，反过来写的话超时会先被 `RequestError` 捕获，永远进不到超时分支。**异常捕获要「从具体到宽泛」。**

**第三层：状态码检查**

```python
if response.status_code != 200:
    print(response.status_code)
    print(response.text)        # 错误详情在这里面
    sys.exit(1)
```

这一层**不能省**，因为 401、402、429 这些**不会抛异常**。对 httpx 来说那是「一次成功完成的 HTTP 往返」，只是内容是拒绝。

常见状态码：

| 码 | 含义 | 排查方向 |
|---|---|---|
| 200 | 成功 | — |
| 401 | 认证失败 | Key 错了，或 `Bearer ` 后少了空格 |
| 402 | 余额不足 | 去平台充值 |
| 400 | 请求体有问题 | 看响应里的 `message` 字段 |
| 429 | 请求太频繁 | 退避重试 |

**实测 401 的响应**：

```
{"error":{"message":"Authentication Fails, Your api key: ***b643 is invalid
(request_id: efe0f983-a512-4cbc-994d-ee8521f4de17)","type":"authentication_error"}}
```

注意 DeepSeek 把 Key 打码成 `***b643` 只露后四位——这是服务商处理敏感信息的规范做法，值得学。

### 1.6 密钥管理

```python
load_dotenv()                            # 把 .env 的内容加载进环境变量
key = os.getenv("DEEPSEEK_API_KEY")      # 按名字取值，取不到返回 None

if not key:                              # 保护代码必须在使用之前
    raise ValueError("未找到 DEEPSEEK_API_KEY，请检查项目根目录下的 .env 文件")
```

三条铁律：

1. **Key 写在 `.env` 里，不写进代码。** 代码要提交到公开仓库，Key 写在里面等于公开发布。
2. **`.env` 必须在 `.gitignore` 里。** 用 `git check-ignore -v .env` 验证——有输出说明被排除了，没输出说明没生效。
3. **验证时不要打印完整 Key。** 用 `print(len(key))` 确认读到了就够了。

> 一旦泄露到公开仓库，会被爬虫在几分钟内扫到并盗刷。第 3 周写 `.dockerignore` 时强调过同一件事。

---

## 第二章 Token 与计费

### 2.1 Token 不是字符

第 3 周写 mock 时用「1 字符 = 1 token」估算，那是权宜之计。真实 token 是**分词器切出来的单位**。

大致规律：

| 文本 | 大约 token 数 |
|---|---|
| 英文常用词 | 1 个 |
| 英文生僻词 | 会被拆成几个 |
| 中文 | 一个字约 0.6 到 1 个 |
| 长数字 | 会被拆开 |
| 标点、空格 | 各占 1 个 |
| 代码 | 符号多，密度高 |

**为什么不按字符算**：模型内部处理的不是字符，而是词表里的编号。分词器负责把文本切成词表里有的片段。所以 token 数取决于**词表怎么切**，不同模型的词表不同，同一段话算出来的数也不一样。

**实测印证**：system + user 加起来约 30 个字符，`prompt_tokens` 是 18。中文确实不到 1 比 1。

### 2.2 价格表（deepseek-flash，低谷价）

| 项目 | 单价（每百万 token） |
|---|---|
| 输入（缓存未命中） | $0.15 |
| 输入（缓存命中） | $0.003 |
| 输出 | $0.6 |

三个关键事实：

1. **输出比输入贵 4 倍**
2. **缓存命中比未命中便宜 50 倍**
3. **高峰期价格翻倍** —— 高峰是工作日 UTC 01:00-04:00、06:00-10:00，换算成北京时间是 **9:00-12:00 和 14:00-18:00**，其余时间（含整个周末）都是低谷

> 晚上和周末做练习，价格直接减半。

### 2.3 缓存机制

```json
"prompt_cache_hit_tokens": 0,
"prompt_cache_miss_tokens": 18
```

缓存匹配的是**请求开头的相同前缀**。如果这次请求的开头和之前某次完全一样，服务端就能复用上次的计算结果。

**由此得出一条工程规则：固定内容放前面，变动内容放后面。**

反例：把时间戳放在 system 最前面

```
第 1 次：system 开头是 "现在是 2026-10-12 23:42"  → 缓存了这个前缀
第 2 次：system 开头是 "现在是 2026-10-12 23:45"  → 第 15 个字符就不一样
```

缓存是**从头逐段比对**的，第一个不匹配的位置之后**全部作废**。时间戳放最前面，意味着后面所有内容（system 剩余部分 + 全部历史对话）都无法复用。

**理想的 messages 顺序，本身就是按「变化频率从低到高」排的**：

```
system（永不变） → few-shot 示例（永不变） → 历史对话（累积） → 新输入（每次变）
```

**实测补充**：缓存有最小长度门槛。实测多轮对话到第 2 轮只有 37 个 token 时，命中数仍是 0——内容太短，服务端认为不值得缓存。要观察到命中，需要 system 写长一些或者多聊几轮。

### 2.4 优化成本前先算清楚大头在哪

一个场景题：把 1000 篇文档（每篇 2000 字）各总结成 100 字，输入和输出哪个成本更高？

```
输入：1000 × 2000 字 ≈ 130 万 token
输出：1000 × 100 字  ≈ 7 万 token
```

输入是输出的近 19 倍。即便输出单价贵 4 倍，**输入的总成本仍然高出约 4.6 倍**。

**这类任务的优化方向和直觉相反**：输出已经很短，压缩空间不大，该想办法的是输入——预处理去掉无关段落，或者利用缓存。

**结论：优化之前先算，不要凭直觉。**

### 2.5 事前估算 vs 事后账单

| 方式 | 时机 | 准确度 | 用途 |
|---|---|---|---|
| 响应里的 `usage` | 事后 | 100%（就是计费依据） | 记账 |
| tiktoken 分词 | 事前 | 近似 | 预算、截断决策 |
| 字符数粗估 | 事前 | 很粗 | 量级判断 |

**tiktoken 对 DeepSeek 不完全准确，但依然有用**，因为它解决的是另一阶段的问题：

1. 防止超出上下文窗口——提前估算就能在超限前主动丢掉早期历史
2. 批量任务跑之前算一遍，避免跑到一半发现要花几百块
3. RAG 场景下决定保留几篇检索结果

**一句话：`usage` 是事后账单，tiktoken 是事前预算。**

### 2.6 CostTracker 实现

```python
class CostTracker:
    """统计多次 API 调用的 token 消耗与累计花费"""

    def __init__(self):
        # 价格直接写成"每 token"，避免每次用的时候都要想一遍除法
        self.price = {"prompt": 0.15 / 1000000, "completion": 0.60 / 1000000}
        # 三个累计器，必须挂在 self 上，方法之间才能共享
        self.calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def record(self, model, usage):
        """记录一次调用，usage 直接传响应里的那个字典"""
        self.calls += 1
        # 用 += 不是 =，这个类的价值就在于累计多次调用
        self.total_prompt_tokens += usage["prompt_tokens"]
        self.total_completion_tokens += usage["completion_tokens"]

    def cost(self):
        """返回累计花费（美元）"""
        cost_prompt = self.price["prompt"] * self.total_prompt_tokens
        cost_completion = self.price["completion"] * self.total_completion_tokens
        return cost_prompt + cost_completion        # 必须 return，否则外面拿到 None

    def report(self):
        """打印统计报告"""
        total_cost = self.cost()        # 调用自己的方法也要加 self.
        print("总调用次数：", self.calls)
        print("总输入token：", self.total_prompt_tokens)
        print("总输出token:", self.total_completion_tokens)
        print(f"总花费: ${total_cost:.6f}")        # .6f 保留 6 位小数
```

**用假数据测试，不花钱也不依赖网络**：

```python
if __name__ == "__main__":
    fake_usage = {"prompt_tokens": 18, "completion_tokens": 21, "total_tokens": 39}
    tracker = CostTracker()
    tracker.record("deepseek-flash", fake_usage)
    tracker.record("deepseek-flash", fake_usage)
    tracker.report()        # 应该是 2 次、36、42、$0.000031
```

> **写工具类的标准做法**：先用假数据把逻辑跑通，再接真实数据。

### 2.7 关于 `self` 的三个认知

这个类写了三遍才对，踩的全是面向对象的入门坑。

**认知一：`self` 是「这个对象自己的储物柜」**

放进柜子（`self.xxx`）的东西，所有方法随时能拿；写成普通变量名的，方法一结束就扔了。

**认知二：类里每个方法的第一个参数都必须是 `self`**

`def cost():` 会报错，`def cost(self):` 才对。调用时 `tracker.cost()` 不用传，Python 会自动把对象本身传进去。

**认知三：为什么类要用 `__init__` 初始化，而脚本直接写在上面就行**

本质是同一条规则：**用之前必须先有值**。区别在于「之前」在哪里。

| | 保证先执行的位置 | 为什么 |
|---|---|---|
| 脚本 | 文件靠上的行 | 从上往下执行，顺序固定 |
| 类 | `__init__` 方法里 | 创建对象时自动调用，必定最先 |

脚本的执行路径只有一条，「写在上面」就等于「先执行」。而类的方法什么时候调、调几次、按什么顺序调，**完全由使用者决定**：

```python
tracker = CostTracker()
tracker.report()        # 使用者可能先调 report
tracker.record(...)     # 再调 record
```

如果把初始化写在 `record` 里，使用者先调 `report` 就会 `AttributeError`。**你没办法要求使用者「必须先调某个方法」**，所以需要一个「创建对象时自动跑一次」的地方，这就是 `__init__`。

> 这也解释了第 1 周学过的规则：**可变对象（列表、字典）必须在 `__init__` 里初始化**。因为每个对象都需要自己独立的一份，而 `__init__` 每创建一个对象就跑一次，正好满足。

---

## 第三章 流式输出

### 3.1 和第 3 周的关系

第 3 周写过一个 SSE 服务，但那是**假的**——回复是自己编的字符串。这一节做的是**真的**。

| 第 3 周（自己 mock） | 第 4 周（真实 API） |
|---|---|
| 自己编的回复逐字 yield | 模型真实生成 |
| `{"type": "delta", "content": char}` | `choices[0].delta.content` |
| 自己发 usage 块 | `stream_options` 让服务器发 |
| 自己写 `data: [DONE]` | 服务器发 `data: [DONE]` |
| 跳过了 TTFT | 这次做出来了 |

**当时是在「扮演服务端」，现在是「客户端」。两边都写过一遍，SSE 这个协议就真的懂了。**

### 3.2 流式和非流式的三个差异

开启只需要一个参数：`"stream": True`。但响应形态完全变了。

```
data: {"id":"...","choices":[{"index":0,"delta":{"content":"SSE"}}]}

data: {"id":"...","choices":[{"index":0,"delta":{"content":"是"}}]}

data: {"id":"...","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

| | 非流式 | 流式 |
|---|---|---|
| 字段名 | `message` | `delta` |
| 内容 | 完整回复 | 一个增量片段 |
| 结束标志 | 响应结束 | 收到 `data: [DONE]` |
| `object` 字段 | `chat.completion` | `chat.completion.chunk` |

**取值路径只差一个词**：

```python
非流式：data["choices"][0]["message"]["content"]
流式：  chunk["choices"][0]["delta"]["content"]
```

**所有块的 `id` 完全相同**，它们属于同一次请求，靠这个 id 归属到一起。

### 3.3 httpx 怎么接收流

```python
with httpx.stream(
    "POST",                      # 第一个参数是方法名字符串，这是和 httpx.post 最大的区别
    url,
    headers=headers,
    json=payload,
    timeout=60,                  # 流式连接保持更久，超时要设大一些
) as response:
    for line in response.iter_lines():
        ...
```

**为什么不能用 `httpx.post`**：它会**等整个响应接收完毕才返回**。即使服务端是流式发送的，用 post 也要等全部发完才能开始处理，和非流式没区别。

`httpx.stream` 在**响应头刚到达时就返回**，响应体留着慢慢读。

**为什么必须配 `with`**：这个连接是「开着的」，读完必须关掉。`with` 保证无论正常结束还是中途报错，连接都会被释放。不关会造成连接泄漏。

> 和第 1 周用 `with open(...)` 读文件是同一个道理：**凡是「用完要关」的资源，都用 `with`**。

### 3.4 逐行解析

```python
full_reply = ""                              # 循环前初始化，不能放循环里

with httpx.stream(...) as response:
    for line in response.iter_lines():
        if not line:                         # 1. 先过滤空行（SSE 的 \n\n 分隔符）
            continue

        payload_str = line.replace("data: ", "")      # 2. 再去掉前缀

        if payload_str == "[DONE]":          # 3. 判断结束标志，必须在 json.loads 之前
            break

        chunk = json.loads(payload_str)      # 4. 解析
        delta = chunk["choices"][0]["delta"]
        content = delta.get("content", "")   # 5. 用 get，第一块和最后一块可能没有 content

        print(content, end="", flush=True)   # 6. 打印并拼接
        full_reply += content
```

**顺序原则：先过滤，再处理。** 空行判断必须在 replace 之前——还没确认这行有内容就先动手处理它，逻辑上是别扭的。这个习惯处理任何数据流都适用。

**`continue` 和 `break` 的区别**：

- `continue` —— 跳过这一轮，继续下一轮（空行后面还有数据）
- `break` —— 整个循环立刻结束（`[DONE]` 后面没有了）

**空 delta 在两个时刻出现**：

- 第一块：通常是 `{"role": "assistant"}`，只声明角色
- 最后一块：`{}` 完全空的，但同一个 chunk 带着 `finish_reason`

所以必须用 `.get("content", "")` 而不是方括号硬取。

> **`.get()` 是字典的方法**，第一个参数是键名，第二个是取不到时的默认值。凡是「这个键可能不存在」的场景都该用它。

**打印的两个参数**：

- `end=""` —— `print` 默认在末尾加换行，流式要的是连续拼接
- `flush=True` —— 强制立即输出。Python 默认会缓冲，攒够一批才写到屏幕，那样就看不到逐字效果了

### 3.5 流式默认不带 usage

因为服务器一边生成一边发，发第一块时还不知道总共会输出多少。

解决办法和第 3 周 mock 时的做法**一模一样**——在最后多发一块只带 usage 的数据：

```python
"stream_options": {"include_usage": True}
```

加了之后，`[DONE]` 之前会多出一块，它的 `choices` 是**空数组**，只有 `usage`。

**这会引入一个坑**：原来那行 `chunk["choices"][0]["delta"]` 遇到这块会抛 `IndexError`（列表索引越界）。所以要先判断：

```python
if chunk.get("usage"):                       # 这块带 usage
    tracker.record("deepseek-flash", chunk["usage"])
    continue                                  # 处理完跳过，不用再取 delta
```

> **当时是自己想出这个设计的，现在发现工业界就是这么做的。** 这不是巧合——流式场景下统计信息只能放最后，这是由问题本身决定的。

### 3.6 TTFT：最重要的性能指标

```python
start = time.perf_counter()                  # 发请求之前
ttft = None                                  # 循环前初始化为 None

# 循环内部，content 赋值之后：
if ttft is None and content:                 # 两个条件缺一不可
    ttft = time.perf_counter() - start

# 循环结束后：
elapsed = time.perf_counter() - start
```

**`ttft is None` 起的是「只记录一次」的作用**。一旦被赋值，后面所有块都进不来。

**`and content` 保证跳过开头的空块**——第一块只有 `{"role": "assistant"}` 没有文字，不该算作「首个 token 到达」。

**实测数据**（两次运行）：

| 指标 | 第一次 | 第二次 |
|---|---|---|
| TTFT | 899 ms | 1226 ms |
| 总耗时 | 1166 ms | 1593 ms |
| TTFT 占比 | **77%** | **77%** |

**拆开看**：第一个字在 899 毫秒时到达，剩下 267 毫秒推完了全部内容。**近 77% 的时间花在「等第一个字」上**，真正生成只占 23%。

这段时间里发生的是网络往返、请求排队、模型加载上下文、生成第一个 token，**和回答有多长基本无关**。

**这就是流式的价值**：非流式要等满 1166 毫秒才看到任何东西，流式 899 毫秒就有反馈了。回答越长差距越大——300 字的回答总耗时可能 8 秒，但 TTFT 仍然是 900 毫秒左右。

**用户感知的「快不快」几乎完全由 TTFT 决定，而不是总耗时。**

### 3.7 为什么肉眼看不到逐字效果

实测时回答只有 30 字，267 毫秒内推完，肉眼确实跟不上。三个验证办法：

1. **让回答变长** —— system 改成「回答 300 字以上」
2. **人为放慢** —— 每块后加 `time.sleep(0.05)`
3. **打时间戳**（最严谨）—— 每块打印 `[{elapsed:.2f}s]`，**时间戳递增就是流式的硬证据**

---

## 第四章 多轮对话与上下文窗口

### 4.1 API 是无状态的

每一次请求对服务器来说都是**完全独立的**。它处理完就忘，不保存任何状态。

**所以「记忆」完全由自己的代码负责**，做法是把历史对话原样塞进 messages 一起发过去：

```
第 1 轮发送：[system, user1]
          收到：assistant1

第 2 轮发送：[system, user1, assistant1, user2]
          收到：assistant2

第 3 轮发送：[system, user1, assistant1, user2, assistant2, user3]
```

模型看到的是一份完整的对话记录，于是表现得像记得一样。**它其实不记得，只是每次都重新读了一遍。**

### 4.2 最容易漏的一步：assistant 回复也要加回去

每轮的完整流程：

```
1. 把用户新消息 append 进 messages
2. 发送整个 messages
3. 拿到回复后，把回复也 append 进 messages（role 是 assistant）
4. 等待下一轮
```

**第 3 步最容易漏。** 只累加用户提问的话，模型看到的是「用户连问了三个问题，中间没有任何回答」，表现会很奇怪。

### 4.3 核心实现

```python
messages = [{"role": "system", "content": "你是一个简洁的助手"}]

while True:
    user_input = input("你: ")

    if user_input in ["quit", "exit"]:       # 判断必须在 append 之前
        break

    messages.append({"role": "user", "content": user_input})

    # ...发请求...

    content = data["choices"][0]["message"]["content"]
    print("AI:", content)

    messages.append({"role": "assistant", "content": content})    # 别漏这步
```

**`in` 的用法**：`user_input in ["quit", "exit"]` 判断「是不是列表里的某一个」，比写两个 `or` 条件清楚。

> 注意不能写成 `user_input == "quit" and user_input == "exit"`——用 `and` 的话永远不成立，一个字符串不可能同时等于两个值。

### 4.4 实测：记忆确实生效

```
你: 我叫张睿文
AI: 你好，张睿文！很高兴认识你。
[messages 2 条 | 输入 14 | 命中 0 | 未命中 14]

你: 我叫什么名字
AI: 你叫张睿文。
[messages 4 条 | 输入 37 | 命中 0 | 未命中 37]
```

**输入 token 从 14 涨到 37，涨了 23**——正好是第 1 轮的「AI 回复 + 新提问」。和理论完全吻合。

> **这个脚本和 DeepSeek 官网调用的是同一个模型。** 区别只在于「外壳」：界面是控制台而不是浏览器，历史存在自己的列表里而不是对方服务器上。**所谓 AI 对话产品，拆开之后只有两样东西：一个无状态的 API，和一个自己维护的消息数组。**

### 4.5 上下文窗口与三种管理策略

messages 会越来越长。deepseek-flash 的窗口是 1M token，但即使没满，**token 越多越贵、越慢**。

| 策略 | 做法 | 优缺点 |
|---|---|---|
| 滑动窗口 | 只保留最近 N 轮 | 简单，但真的会忘 |
| **保留 system + 最近 N 轮** | system 永不丢，只截断历史 | **最常用** |
| 摘要压缩 | 让模型总结早期对话 | 保留信息但要额外调用 |

**为什么 system 必须保留**：它定义了模型的身份和规则。丢掉之后，system 里写的「回答五十字以内」就失效了，模型会开始长篇大论；如果定义了「你是客服，只回答产品问题」，丢掉后它会开始聊任何话题。

**滑动窗口实现要点**（第 1 周 `ToolRegistry` 的 `_trim` 用过同样的写法）：

```python
# messages[0] 是字典，切片结果是列表，类型不同不能直接相加
[messages[0]] + messages[-limit:]        # ✅ 把字典包成单元素列表
messages[0] + messages[-limit:]          # ❌ 报错
```

判断是否超限时要 `len(messages) - 1`，把 system 那条排除掉，它不占轮次配额。

### 4.6 为什么长对话会变慢

输入越长，**TTFT 越大**——模型「读完上下文」所需的时间更久。而生成速度基本不变。

这和第三章测出的 77% 分布是吻合的：慢在读，不在写。

---

## 第五章 Prompt 工程与 JSON Mode

### 5.1 Prompt 工程不是说话技巧

它的本质是：**给一个没有上下文的系统提供足够的信息和约束，让输出落在你要的范围内。**

模型不知道你的业务、不知道你要拿输出干什么、不知道你期望的格式。**这些都得你说清楚。**

### 5.2 一个好的 system 包含三部分

| 部分 | 作用 | 示例 |
|---|---|---|
| **身份** | 定调，影响语气和详细程度 | 你是一个简历信息抽取助手 |
| **规则** | 必须怎么做、不能怎么做 | 只输出事实，不做推测 |
| **边界** | 遇到意外情况怎么办 | 信息缺失时填 null |

**边界最容易被忽略，但最重要。** 模型遇到意料之外的输入时，默认行为往往是「编一个」。

### 5.3 Few-shot：示范比描述有效

```python
messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "示例输入1"},
    {"role": "assistant", "content": "示例输出1"},    # 这是自己写的，不是模型生成的
    {"role": "user", "content": "示例输入2"},
    {"role": "assistant", "content": "示例输出2"},
    {"role": "user", "content": "真正的输入"},
]
```

**代价是 token**——每个示例都占输入，而且每次请求都要重发。

**但在多轮场景下代价没那么大**：few-shot 示例位置固定（紧跟 system 之后）、内容永不变化，**正好是缓存最理想的对象**，命中后单价便宜 50 倍。

### 5.4 为什么需要结构化输出

```
模型输出：这位候选人叫张三，本科学历，有三年Python经验
你的代码：怎么从这句话里可靠地取出"学历"字段？
```

正则或字符串切分都极其脆弱——模型换个说法就全崩了。所以要让模型**直接输出 JSON**。

**三种实现方式**：

| 方式 | 可靠性 | 说明 |
|---|---|---|
| 只在 prompt 里要求 | 低 | 模型常加前后缀 |
| **JSON Mode** | 高 | 服务端保证合法 JSON |
| Function Calling | 最高 | 连字段类型都能约束（第 5 周） |

**为什么「只在 prompt 里要求」不可靠**：模型经常画蛇添足，输出变成「好的，以下是抽取结果：\`\`\`json {...} \`\`\` 希望对你有帮助！」，前后多了说明文字和代码块标记，`json.loads` 直接报错。

### 5.5 JSON Mode 的两个前提条件

```python
"response_format": {"type": "json_object"}
```

**必须同时满足**：

1. **prompt 里必须包含 "json" 这个词**，否则报错
2. **prompt 里最好给出期望的 JSON 结构示例**，否则字段名可能乱来

### 5.6 实战：简历信息抽取

**第一版 system（只有身份 + 结构）**

```
你是一个简历信息抽取助手。从用户提供的简历文本中抽取信息，以 json 格式输出，结构如下：
{
  "name": "姓名",
  "education": "最高学历",
  "skills": ["技能1", "技能2"],
  "years_of_experience": 工作年限数字
}
```

**第一版输出**：

```json
{
  "name": "李明远",
  "education": "硕士",
  "skills": ["Python", "Go", "MySQL", "Redis", "Kafka", "Docker", "Kubernetes"],
  "years_of_experience": 1
}
```

逐字段分析：

| 字段 | 输出 | 评价 |
|---|---|---|
| name | 李明远 | ✅ |
| education | 硕士 | ⚠️ 对了，但**是运气** |
| skills | 七项技术，没混进"英语六级" | ⚠️ 同样是运气 |
| years_of_experience | **1** | ❌ 实际应为 3 |

**为什么说「对了也是运气」**：system 里**没有任何一条规则**说过「取最高学历」「只要技术技能」。模型这次按常识猜对了，但换一份简历、换个模型版本，都可能给出不同结果。**生产系统里，依赖模型的常识猜测是不可接受的。**

**为什么 years 算错了**：简历写的是「2023.07-至今」。**模型不知道「今天是几号」**——训练数据有截止时间，而且每次请求独立，没人告诉它当前日期。「至今」这个词对它来说是悬空的。

### 5.7 补规则后的对比

**补充的规则**：

```
规则：
- education 填最高学历，格式为"学位 专业"，例如：硕士 软件工程
- skills 只包含技术技能，不包含语言能力、证书、获奖经历
- years_of_experience 根据工作经历起止时间计算，"至今"按当前日期算，取整数年
- 任何字段在简历中找不到对应信息时，填 null，严禁编造或推测

当前日期：2026-10-13
```

**注意当前日期放在最末尾**——它每天都变，放开头会让整个 prompt 的缓存失效。

**对比结果**：

| 字段 | 补规则前 | 补规则后 |
|---|---|---|
| education | 硕士 | **硕士 软件工程** |
| years_of_experience | 1 | **3** |
| 输入 token | 261 | 352 |

**years 从 1 变成 3，不是模型变聪明了，是给了它原本缺失的信息。**

**代价**：输入 token 多了 91 个。**规则是要花钱的，但换来的是确定性。** 好消息是 system 内容固定，多轮调用能命中缓存。

### 5.8 幻觉测试：最有价值的一步

把简历里的**教育背景整段删掉**，再跑一次：

```json
{"name": "李明远", "education": null, "skills": [...], "years_of_experience": 3}
```

**模型老实填了 null，没有编造。** 而且其他字段不受影响——说明规则是精确生效的，不是让模型整体变保守。

**模型编造信息（幻觉）是大模型应用最大的风险之一。** 它不会说「我不知道」，而是会自信地给一个看起来合理的答案。在简历抽取这种场景下，编造一个学历可能导致严重后果。

**对抗幻觉的第一道防线，就是在 prompt 里明确规定「找不到就填 null」。** 很多人写 prompt 只说要什么，不说找不到时怎么办，模型的默认行为就是编一个。

### 5.9 永远不要假设模型会遵守格式

即使开了 JSON Mode，解析也可能失败（比如被 `max_tokens` 截断）：

```python
try:
    result = json.loads(content)
except json.JSONDecodeError as e:
    # 记录原始输出，方便排查
    ...
```

**更进一步**：对枚举类型的输出要做值校验。

```python
if result["sentiment"] not in ["正面", "负面", "中性"]:
    # 模型输出了预期之外的值，重试 / 降级 / 报警
```

few-shot、JSON Mode、`temperature=0` **都只是「提高概率」，没有任何一种能保证 100%**。模型偶尔会输出「偏正面」「中性偏负」这种东西。

**把模型当成「大概率正确但会出错的外部服务」来对待，而不是确定性的函数。**

---

## 第六章 典型错误合集

> ⚠️ **本章所有标记 ❌ 的代码都是错误示范，请勿复制使用。**
> 按根因分类而非时间顺序，归类后能看出反复犯错的模式。

### 根因一：嵌套结构取值（本周最高频，5 次）

---

**错误 1：从响应对象直接取值，忘了 `.json()`**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
content = response["choices"][0]["message"]["content"]
```

**原因**：`response` 是 httpx 的**响应对象**，不是字典。它身上有 `.status_code`、`.text`、`.json()` 这些属性和方法，但不支持方括号索引。

**✅ 正确做法**：先转成字典。

```python
data = response.json()        # 把响应体的 JSON 解析成 Python 字典
content = data["choices"][0]["message"]["content"]
```

> 服务器发回来的是一串**文本**，Python 不知道它是 JSON。`.json()` 相当于 httpx 封装好的 `json.loads(response.text)`。

---

**错误 2：`finish_reason` 的层级多走了一层**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
finish_reason = data["choices"][0]["message"]["finish_reason"]
```

报错：`KeyError: 'finish_reason'`

**原因**：`message` 里只有 `role` 和 `content`。`finish_reason` 和 `message` 是**兄弟关系**，都挂在 `choices[0]` 下面。

**✅ 正确做法**：

```python
finish_reason = data["choices"][0]["finish_reason"]
```

---

**错误 3：把字典当成列表取值**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
prompt = usage[0]["message"]["prompt"]
```

三个问题叠在一起：`usage` 是字典不是列表、里面没有 `message` 这个键、键名不是 `prompt`。

**✅ 正确做法**：

```python
usage = data["usage"]                     # usage 在最外层，和 choices 平级
prompt = usage["prompt_tokens"]           # 只需要再走一层
```

**两种括号的区别**：

| 容器 | 方括号里放什么 | 例子 |
|---|---|---|
| 字典 | 键名（字符串，带引号） | `usage["total_tokens"]` |
| 列表 | 下标（数字，从 0 开始） | `choices[0]` |

整个响应里只有 `choices` 是列表，所以全脚本应该只出现一次 `[0]`。

---

**错误 4：键名写短（本周犯了两次）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
prompt = usage["prompt"]           # 实际键名是 prompt_tokens
hit = usage["hit"]                 # 实际是 prompt_cache_hit_tokens
```

报错：`KeyError: 'prompt'`

**原因**：**键名必须一字不差**，包括下划线、大小写、单复数。Python 不会猜你的意思。

**✅ 排查办法**：遇到 `KeyError` 不要猜，直接打印有哪些键。

```python
print(usage.keys())        # 一行代码两秒钟，比猜快得多
```

> **这个错犯了两次**，第 1 节和第 4 节各一次。说明还没形成肌肉记忆——以后取值前先看一眼键名。

---

**两种 Error 的区别**（本周都遇到了，容易混）：

| 报错 | 含义 | 触发写法 |
|---|---|---|
| `KeyError` | 字典里没这个键 | `usage["prompt"]` |
| `AttributeError` | 对象身上没这个属性或方法 | `tracker.total_prompt` |

**方括号取不到 → KeyError；点号取不到 → AttributeError。**

---

### 根因二：面向对象与 `self`

---

**错误 5：方法漏写 `self` 参数**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
class CostTracker:
    def cost():                   # 括号是空的
        ...
    def report():
        ...
```

**✅ 正确做法**：类里每个方法的第一个参数都必须是 `self`。

```python
def cost(self):
    ...
```

---

**错误 6：局部变量没挂到 `self` 上**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def __init__(self):
    price = {"prompt": 0.15, "completion": 0.60}      # 局部变量，__init__ 结束就消失
    total_prompt_tokens = 0                            # 同样
```

**后果**：`cost` 方法里用 `self.price` 会报 `AttributeError`。

**✅ 正确做法**：想在方法之间共享的数据，必须写成 `self.xxx`。

---

**错误 7：属性名和方法名重名**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
class CostTracker:
    def __init__(self):
        self.record = 0           # 属性叫 record
    def record(self, model, usage):    # 方法也叫 record
        ...
```

**后果**：`__init__` 把 `self.record` 设成 0 之后，这个对象的 `record` 就变成了数字，调用 `tracker.record(...)` 会报「int 不可调用」。

**✅ 正确做法**：计数器换个名字，比如 `self.calls`。

---

**错误 8：用 `=` 而不是 `+=`，累加变覆盖**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def record(self, model, usage):
    self.total_prompt_tokens = usage["prompt_tokens"]      # 每次都覆盖
```

**后果**：调用十次，最后只剩第十次的数字。**这个类存在的意义就是统计累计量。**

**✅ 正确做法**：

```python
self.total_prompt_tokens += usage["prompt_tokens"]
```

> `=` 是「替换成新值」，`+=` 是「在原有基础上加」。

---

### 根因三：控制流与作用域

---

**错误 9：except 接住异常却没终止程序**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
try:
    response = httpx.post(..., timeout=0.001)
except httpx.TimeoutException as e:
    print("超时了:", e)
# 程序继续往下走……
print(response.status_code)        # response 从未被赋值
```

报错：

```
超时了: _ssl.c:1064: The handshake operation timed out
Traceback (most recent call last):
  ...
NameError: name 'response' is not defined
```

**原因**：**`except` 处理完异常后，程序会继续执行后面的代码。** 它只是「接住」了错误，不是「停止」程序。而赋值在超时时根本没完成，`response` 压根不存在。

**✅ 三种解决办法**：

```python
# 办法一：出错就退出（推荐，结构最灵活）
except httpx.TimeoutException as e:
    print("超时了:", e)
    sys.exit(1)

# 办法二：把后续代码也放进 try（try 块会很长）

# 办法三：用 else 分支（只在没出错时执行）
try:
    response = httpx.post(...)
except ...:
    ...
else:
    print(response.status_code)
```

> **接住了错误，却没有阻止后续代码运行**——这是异常处理最常见的坑。

---

**错误 10：判断写在了循环外面，引用了还不存在的变量**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
ttft = None
if ttft is None and content:        # content 是循环内才产生的变量
    ttft = time.perf_counter() - start

with httpx.stream(...) as response:
    for line in response.iter_lines():
        ...
```

两个问题：`content` 此时不存在会报 `NameError`；而且这个判断只会执行一次，逻辑上也不对——需要的是**每收到一块就检查一次**。

**✅ 正确做法**：放进循环，紧跟在 `content` 赋值之后。

---

**错误 11：退出判断写在 append 之后**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
user_input = input("你: ")
messages.append({"role": "user", "content": user_input})
if user_input == "quit":           # 已经晚了，quit 被当成普通消息发出去了
    break
```

**实测现象**：输入 `quit` 后模型回了「好的，再见」，然后才退出——白白多花了一次钱。

**✅ 正确做法**：读到输入后**立刻判断**，确认不是退出指令再往下走。

---

**错误 12：`tracker.report()` 放在循环里面**

每轮都打印一次完整统计，对话到第五轮时屏幕上已经刷了五份报告。

**✅ 正确做法**：`record` 留在循环里（每轮都要记录），`report` 放在循环结束之后（只汇报一次）。

---

**错误 13：累加容器没有预先初始化**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
for line in response.iter_lines():
    full_reply += content          # full_reply 从未定义
```

**✅ 正确做法**：循环**之前**初始化。

```python
full_reply = ""                    # 字符串用 "" 起步
```

**通用套路**：先定义一个「容器」，再在循环里往里累加。

| 场景 | 初始值 | 循环里的操作 |
|---|---|---|
| 数 token | `0` | `+= 1` |
| 累计用量 | `0` | `+= usage[...]` |
| 拼接回复 | `""` | `+= content` |
| 收集结果 | `[]` | `.append(...)` |

---

### 根因四：API 参数与协议

---

**错误 14：`True` 拼写成 `Ture`**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
"stream": Ture
```

报错：`NameError: name 'Ture' is not defined`

**原因**：Python 把 `Ture` 当成了一个从未定义的变量名。

**✅ 正确做法**：`True`，首字母大写。小写的 `true` 同样会报错（**JSON 里是小写，Python 里是大写**，这两者刚好相反）。

---

**错误 15：`httpx.stream` 漏了方法名**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
with httpx.stream(url, headers=headers, json=payload) as response:
```

**原因**：`httpx.stream` 是通用的，GET、POST、PUT 都能用它做流式，所以**方法名必须单独传**。

**✅ 正确做法**：

```python
httpx.post(url, ...)              # 方法名体现在函数名里
httpx.stream("POST", url, ...)    # 方法名要单独传，是第一个参数
```

---

**错误 16：`httpx.stream` 直接赋值，没用 `with`**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
response = httpx.stream("POST", url, ...)
for line in response.iter_lines():       # 报错：对象没有这个方法
```

**原因**：`httpx.stream()` 返回的是一个**上下文管理器**，不是响应对象。

**✅ 正确做法**：用 `with ... as response`，所有读取操作都写在缩进块里面。出了这个块连接就关闭了。

---

**错误 17：URL 字符串没加引号**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
response = httpx.post(
    url,https://api.deepseek.com/v1/chat/completions
)
```

**原因**：被理解成两个参数，而且 `https://...` 没有引号，不是合法的 Python 语法。

**✅ 正确做法**：地址是字符串，必须用引号包起来。

```python
url = "https://api.deepseek.com/v1/chat/completions"
response = httpx.post(url, headers=headers, json=payload, timeout=30)
```

---

**错误 18：f-string 忘了加 `f`**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
"Authorization": "Bearer key"      # 变量 key 的值根本没进去
```

**后果**：服务器收到的 Key 字面上就是 "key" 三个字母，返回 401。

**✅ 正确做法**：

```python
"Authorization": f"Bearer {key}"
```

**验证办法**：`print(headers["Authorization"][:10])`，应输出 `Bearer sk-`。如果输出 `Bearer ke`，说明 f 没加上。

---

### 根因五：模型行为与成本

---

**错误 19：不知道思考模式默认开启，花钱买了个空回答**

**现象**（`max_tokens=200`）：

```json
"content": "",                                 ← 正式回答是空的
"reasoning_content": "我们需要回答用户中文问题……",  ← 推理过程占满了
"finish_reason": "length",                     ← 被截断了
"usage": {
  "completion_tokens": 200,
  "completion_tokens_details": { "reasoning_tokens": 200 }    ← 200 个全用在推理上
}
```

**原因**：`deepseek-flash` **默认开启思考模式**，模型先推理再回答。200 的上限在推理阶段就用完了，还没轮到写正式答案就被强制停止。**花了钱，什么都没拿到。**

**✅ 解决办法**（查官方文档得到）：

```python
"thinking": {"type": "disabled"}
```

**开关前后对比**：

| 指标 | 思考模式开 | 思考模式关 |
|---|---|---|
| prompt_tokens | 43 | 18 |
| completion_tokens | 200（全是推理） | 21 |
| content | 空 | 完整回答 |
| finish_reason | length | stop |

**输出 token 降到十分之一，结果反而是完整的。**

**结论：思考模式不是「免费变聪明」，它用 token 换准确率。** 简单任务（翻译、分类、格式转换、闲聊）关掉更划算；难题（数学推理、复杂代码、多步规划）才值得开。还可以用 `reasoning_effort` 设 `low/high/max` 做精细权衡，不必非黑即白。

> **推理 token 算在输出里，是要计费的。**

---

**错误 20：不写规则，模型就自由发挥**

见 5.6 节的完整对比。只给结构不给规则时，`education` 和 `skills` 碰巧对了（靠常识猜的），`years_of_experience` 直接错了。

**✅ 正确做法**：把每一个歧义点都写成明确规则。**哪条规则没写清楚，模型就在哪里自由发挥。**

---

### 错误统计

| 根因分类 | 次数 |
|---|---|
| 嵌套结构取值 | 5 |
| 面向对象与 self | 4 |
| 控制流与作用域 | 5 |
| API 参数与协议 | 5 |
| 模型行为与成本 | 2 |

**本周最该记住的两条**：

1. **遇到 `KeyError` 先打印 `.keys()`，不要猜。** 同一个错犯了两次，说明「取值前先确认结构」还没变成本能。
2. **`except` 不等于终止。** 接住异常后必须明确决定程序怎么走，否则后面的代码会带着不存在的变量继续跑。

---

## 第七章 本周自检

- [x] 能手写一个完整的 `/v1/chat/completions` 请求（头、体、三层防护）
- [x] 能说清 system / user / assistant 三种 role 的分工
- [x] 知道 `temperature=0` 的真正意义是「可复现」而非「更准确」
- [x] 能从嵌套响应里精确取出 content、finish_reason、usage
- [x] 知道 token 不等于字符，取决于分词器
- [x] 能说清输入、输出、缓存三种价格的差异与量级
- [x] 知道「固定内容放前面」这条缓存规则的由来
- [x] 能写出一个可复用的统计类，并解释 `self` 和 `__init__` 的必要性
- [x] 能说清流式与非流式在字段、结束标志、接收方式上的差异
- [x] 知道为什么流式必须用 `with httpx.stream`
- [x] 能测量 TTFT 并解释它为什么比总耗时更重要
- [x] 能自己实现多轮对话的"记忆"，并说清 API 是无状态的
- [x] 知道滑动窗口为什么必须保留 system
- [x] 能写出包含身份、规则、边界三部分的 system prompt
- [x] 知道 JSON Mode 的两个前提条件
- [x] 知道对抗幻觉的第一道防线是明确规定"找不到填 null"

---

## 附录 A：本周完整参数速查

```python
payload = {
    "model": "deepseek-flash",              # 或 deepseek-v4-pro
    "messages": [...],                      # 对话数组，顺序有意义
    "temperature": 0,                       # 0=可复现，1=默认，>1.5 可能语无伦次
    "max_tokens": 500,                      # 输出上限，被截断时 finish_reason=length
    "thinking": {"type": "disabled"},       # 关闭思考模式（默认是开启的）
    "stream": True,                         # 流式返回
    "stream_options": {"include_usage": True},   # 流式时最后多发一块 usage
    "response_format": {"type": "json_object"},  # JSON Mode，需 prompt 含 "json"
}
```

**可选：思考强度控制**

```python
"reasoning_effort": "low"        # low / high / max，在成本和准确率之间权衡
```

## 附录 B：取值路径速查

```python
data = response.json()

# 非流式
data["choices"][0]["message"]["content"]
data["choices"][0]["finish_reason"]

# 流式（单个 chunk）
chunk["choices"][0]["delta"].get("content", "")
chunk.get("usage")                           # 只有最后一块才有

# 用量（两者相同）
usage = data["usage"]
usage["prompt_tokens"]
usage["completion_tokens"]
usage["total_tokens"]
usage["prompt_cache_hit_tokens"]
usage["prompt_cache_miss_tokens"]
```

## 附录 C：提交记录

```
week4: first DeepSeek API call with error handling
week4: CostTracker for token usage and cost
week4: integrate CostTracker into first_call
week4: streaming call with TTFT and usage tracking
week4: multi-turn conversation with usage stats
week4: prompt engineering and JSON mode extraction
```

---

## 遗留任务

- 多轮对话的**滑动窗口**裁剪（第 4 节进阶，已掌握写法未落地）
- Few-shot 版本的简历抽取，与纯规则版对比效果
- 用 tiktoken 做发送前的 token 预估

---

## 下周预告

第 5 周：**Function Calling 与 Agent 雏形**。

模型将不只是回答问题，而是能说「我需要调用天气查询工具，参数是北京」，然后由代码去执行，把结果喂回去，模型再基于结果继续决策。**这个循环才是 Agent 的本质。**

本周学的每一样东西都会用上：messages 数组会多出 `tool` 这个 role，JSON Mode 的约束思路会升级成函数签名声明，而「永远校验模型输出」这条原则会变得更加重要——因为这次模型的输出不再只是给人看的文字，而是**要被代码执行的指令**。
