# 第 5 周技术总结：Function Calling 与 Agent 循环

> 16 周 AI Agent 应用开发学习记录 · 第 5 周
> 关键词：Function Calling、工具描述、消融实验、Agent 循环、并行调用、错误回填、Embedding、Transformer

---

## 本周概览

前四周模型只会**说话**：回答问题、流式输出、抽取 JSON，输出都是一段给人读的文本。

这一周模型开始**要求做事**：

```
用户：北京和上海温差多少度？
模型：我要调 get_weather，查北京和上海          ← 模型提出调用
代码：执行函数，得到 12℃ 和 18℃                ← 你的代码执行
模型：我要调 calculate，算 18 - 12              ← 模型根据结果继续决策
代码：执行函数，得到 6
模型：北京比上海低 6℃。                         ← 模型给出最终回答
```

**Agent 的全部能力都建立在这个循环上。** 搜索、读文件、查数据库、调别的 API，本质都是「模型提出调用，代码执行，结果回填」。

| 小节 | 内容 | 产出文件 |
|---|---|---|
| 1 | 五步循环 | `function_call.py` |
| 2 | 工具描述质量与消融实验 | `tool_ablation.py` |
| 3 | 并行调用与多轮工具循环 | `agent_loop.py` |
| 4 | 错误处理与结果回填 | `agent_loop.py`（在第 3 节基础上修改） |
| 5 | 概念补课 | 无代码 |

**本周最有分量的产出**：一组自己设计、自己跑出来的工具描述消融实验数据（详细描述 100% vs 模糊描述 70%），以及一个能自主多轮调用、出错不崩溃的 Agent 循环。

**代码仓库**：`https://github.com/Ruiwen-ZHANG/ai-agent-learning`

---

## 第一章 Function Calling 五步循环

### 1.1 最大的误解：模型不执行函数

模型做的事情只有一件：**生成文本**。所谓「调用工具」，是它生成了一段结构化文本，大意是「我想调 `get_weather`，参数是北京」。

**真正执行函数的是你的 Python 代码。** 模型甚至不知道你有没有真的执行，它只能等你把结果发回去。DeepSeek 官方文档原话：「The model itself does not execute specific functions」。

### 1.2 为什么需要工具：模型的知识是封闭的

模型没有网络、没有时钟、没有数据库。问它北京今天多少度，不给工具的话它只有两种反应：

- **诚实**：「我无法获取实时天气」
- **危险**：编一个看起来合理的温度（幻觉）

**工具是模型唯一的对外通道。** 天气、股价、数据库记录、用户文件，凡是模型不可能知道的东西，都要靠工具。

> **官网为什么能直接回答天气？** 因为 DeepSeek 官网不是裸模型，它是一个**产品**：模型外面包了一层内置工具（联网搜索）。你在网页上看到的「一问一答」，后台至少是两次模型调用，只是工具调用过程被界面折叠了。关掉联网搜索再问实时信息，它要么拒绝，要么编。
>
> 第 4 周说「我的脚本和官网调同一个模型」是对的，但要补一句：**同一个模型，不同的产品**。差的就是工具这一层。

### 1.3 五步流程

```
┌─ 1. 把工具的 JSON Schema 描述随请求发给模型
├─ 2. 模型返回 tool_calls：要调哪个工具、传什么参数
├─ 3. 【你的代码】解析参数，执行函数
├─ 4. 把执行结果作为 role:"tool" 的消息追加进 messages，再发一次请求
└─ 5. 模型基于结果生成最终回答
```

**一次完整的工具调用至少是两次 API 请求**，费用和延迟都按两次算。

### 1.4 工具声明

`tools` 是 payload 的**顶层字段**，和 `model`、`messages` 平级，**不要放进 messages，也不要写进 system**：

```python
tools = [                                    # 最外层是列表，可以放多个工具
    {
        "type": "function",                  # 目前只有 function 一种类型
        "function": {
            "name": "get_weather",           # 函数名，模型会原样返回
            "description": "当用户询问气温、天气状况、是否下雨、冷热时，查询指定城市的当前天气。"
                           "不要用于天气预报、历史天气，不要用于与天气无关的问题。",
            "parameters": {                  # 参数用 JSON Schema 描述
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市中文名，不含'市'字，例如：北京、上海",
                    }
                },
                "required": ["location"],    # 必填参数
            },
        },
    },
]
```

| 位置 | 放什么 | 作用 |
|---|---|---|
| `system` | 你是谁、怎么做事 | 定调、约束行为 |
| `tools[].description` | 这个工具干什么、何时用 | 让模型判断要不要调 |

> **工具能力靠 `tools` 声明，不靠 prompt 描述。** user 里写「需要调用哪些工具？」会把问题变成「介绍一下你的工具」，模型可能用文字描述而不是真的返回 `tool_calls`。真实用户只会说「北京今天多少度」。

### 1.5 模型返回什么

```json
{
  "role": "assistant",
  "content": "",
  "tool_calls": [
    {
      "index": 0,
      "id": "call_00_J6hHJNp8mVJSw1DlNFmF8896",
      "type": "function",
      "function": {
        "name": "get_weather",
        "arguments": "{\"location\": \"北京\"}"
      }
    }
  ]
}
```

同时 `finish_reason` 变成 **`tool_calls`**：

| finish_reason | 含义 |
|---|---|
| `stop` | 正常说完 |
| `length` | 撞到 max_tokens 被截断 |
| `tool_calls` | 模型要调工具 |

**三个必须记住的细节**：

1. **DeepSeek 返回的 `content` 是空字符串 `""`，不是 `null`。** OpenAI 返回 null，两者都"合规"。所以判断条件不要写 `content is None`，最稳的是 `"tool_calls" in message`：直接检查你真正要用的数据在不在
2. **`arguments` 是 JSON 格式的字符串，不是字典。** 必须 `json.loads` 之后才能取值
3. **`tool_calls` 里多了一个 `index` 字段**，这是 DeepSeek 特有的，不影响使用

### 1.6 两个容易混的字段

| 字段 | 方向 | 出现在哪 |
|---|---|---|
| `tool_calls` | 模型 → 你 | 响应的 message 里 |
| `tool_calls[i]["id"]` | 模型 → 你 | 每次调用的唯一标识 |
| `tool_call_id` | **你 → 模型** | **你回填时自己写的**，值取自上面那个 id |

名字很像，一个是收到的，一个是发出的。

### 1.7 结果回填

```python
message = data["choices"][0]["message"]     # 模型那条带 tool_calls 的回复
messages.append(message)                    # 1. 先把它原样追加回去

messages.append({                           # 2. 再追加执行结果
    "role": "tool",                         # 第四种 role
    "tool_call_id": tool_call_id,           # 必须和上面那条的 id 对应
    "content": weather,                     # 必须是字符串
})
```

**为什么模型说过的话还要原样发回去？** API 是无状态的（第 4 周核心认知）。服务器处理完第一次请求就忘了，不记得自己说过「我要调 get_weather」。只发工具结果的话，模型会不知道这个结果是回应谁的。

**为什么工具结果要自己构造？** 时间顺序决定的：收到响应 → 你的函数才开始执行 → 函数返回结果。**函数结果绝不可能出现在响应里**，那一刻函数还没跑。

回填后 messages 共 4 条：

| # | role | 来源 |
|---|---|---|
| 1 | system | 一开始写的 |
| 2 | user | 一开始写的 |
| 3 | assistant | 从响应里取（模型说的） |
| 4 | tool | 自己构造（函数返回的） |

### 1.8 引用：两种追加写法是同一件事

```python
messages = [...]
payload = {"messages": messages, ...}

messages.append(x)               # 改法一
payload["messages"].append(x)    # 改法二
```

**两行效果完全一样。** `payload["messages"]` 和 `messages` 指向**同一个列表对象**，字典里存的是引用，不是副本。

```python
a = [1, 2]
d = {"x": a}
a.append(3)
print(d["x"])    # [1, 2, 3]，d 也跟着变了
```

这和第 1 周的类属性陷阱、可变默认参数陷阱是同一个原理：**可变对象是原地修改，不管几个名字指向它，改一个全都变。**

两个推论：

- **append 只增不减。** 第一次请求发了什么，依然完整保留在 messages 的前两条里。messages 本身就是完整的历史记录
- **想保存每次请求的快照，必须 `copy.deepcopy`。** 直接 `history.append(messages)` 存的还是引用，后面一 append，历史记录也会跟着变

### 1.9 实测数据

**第一次请求**（带 tools）：

```json
"prompt_tokens": 295,
"completion_tokens": 38,
"prompt_cache_hit_tokens": 0
```

对比第 4 周问「什么是 SSE」只有 18 个 prompt token。**多出来的 277 个几乎全是 tools 声明。**

**第二次请求**（回填后）：

```json
"prompt_tokens": 351,
"completion_tokens": 8,
"prompt_cache_hit_tokens": 128,
"prompt_cache_miss_tokens": 223
```

最终回答：`"北京今天 12℃，天气晴。"`

| 观察 | 含义 |
|---|---|
| completion 从 38 降到 8 | 第二次模型几乎不用思考，只是把 `"北京今天 12℃，晴"` 转述成一句话。**真正的工作是函数做的，模型只是翻译** |
| 缓存命中 128 | 第二次请求的开头（tools + system + user）和第一次完全一样。**这是第 4 周讲的缓存第一次真正在眼前发生** |
| prompt 多了 56 | 就是追加的那两条消息 |
| 回答里出现「12℃」「晴」 | 这两个信息模型不可能知道，**来自本地函数**，闭环成立 |

**对照实验：问「你好」**

```json
"content": "你好！我是天气查询助手，可以帮你查询任意城市的当前天气。告诉我你想查哪个城市吧，比如"北京"或"上海"。",
"finish_reason": "stop",
"prompt_tokens": 291
```

- 没有 `tool_calls` 这个键，模型判断出打招呼不需要调用。**工具调用是模型的自主决策，不是机械触发**
- 它知道自己有什么工具（「可以帮你查询任意城市的当前天气」），因为 tools 声明就在上下文里
- `prompt_tokens` 仍然是 291：**tools 声明不管用不用都要付费**。挂十个工具，每次请求都背着几千 token 的声明

### 1.10 CostTracker 开始产生误差

两次请求共命中 256 个缓存 token。按实际价格计算：

| 项目 | token | 单价 | 小计 |
|---|---|---|---|
| 输入（未命中） | 390 | $0.15/M | $0.0000585 |
| 输入（命中） | 256 | $0.003/M | $0.0000008 |
| 输出 | 46 | $0.6/M | $0.0000276 |
| **合计** | | | **约 $0.000087** |

CostTracker 报的是 $0.000124，**偏高约 40%**，因为它把所有输入都按未命中价算。

第 4 周写 CostTracker 时这是「等真需要了再加」的简化。**简化在当时是对的，失效的时机也是可以预见的**：Agent 轮次越多，缓存命中率越高，误差越大。

---

## 第二章 工具描述质量与消融实验

### 2.1 description 是模型的判断依据

模型看不到你的函数实现，不知道 `get_weather` 里是查数据库还是 `return "12℃"`。它能看到的只有：**函数名、描述文字、参数描述**。

**模型能力决定它猜得多准，描述质量决定它有没有东西可猜。**

- 靠常识能推出来的，强模型确实更会猜（「北京冷不冷」算天气问题）
- **你业务特有的约束，任何模型都推不出来**（「只能查今天」「城市名必须传英文」「超过 7 天的数据查不到」）

### 2.2 好描述的四个要素

| 要素 | 作用 | 例子 |
|---|---|---|
| **做什么** | 基本功能 | 查询城市的当前天气 |
| **什么时候用** | 触发条件 | 当用户询问气温、天气状况、是否下雨、冷热时 |
| **什么时候不用** | 边界 | 不要用于天气预报、历史天气 |
| **参数格式** | 怎么填 | 城市中文名，不含「市」字，如「北京」 |

「什么时候不用」最容易漏，但在多工具场景下最关键。

### 2.3 四种失败模式

| 失败模式 | 原因 | 表现 |
|---|---|---|
| **该调不调** | 描述太窄或太模糊 | 「北京冷不冷」没识别为天气问题 |
| **不该调乱调** | 描述太宽泛 | 「北京有什么好玩的」也去查天气 |
| **调了但参数错** | 参数描述不清 | 传了「北京市」，函数只认「北京」 |
| **多工具选错** | 描述重叠 | 该查预报却调了实时天气 |

> **参数错了的三种修法，从糙到好**：改参数描述 → 用 `enum` 限定取值 → **函数内部做映射兜底**。能用代码确定性完成的事，不要指望模型每次都对。

### 2.4 实验设计

**关键认知一：temperature=0 时，同一个问题重复跑 20 次没有统计意义。** 随机性被关掉了，20 次结果完全一样，只是把成本乘了 20。

**有意义的做法：固定描述，换不同的问题。** 设计一个测试集：

| # | 问题 | 预期 | 类型 |
|---|---|---|---|
| 1 | 北京今天多少度 | True | 正样本：直接问气温 |
| 2 | 上海现在天气怎么样 | True | 正样本：出现「天气」二字 |
| 3 | 深圳热不热 | True | 正样本：**不含「天气」，考理解** |
| 4 | 广州现在下雨吗 | True | 正样本：问具体现象 |
| 5 | 杭州要穿外套吗 | True | 正样本：**间接，需推理** |
| 6 | 北京有哪些好玩的景点 | False | **困难负样本：有地名** |
| 7 | 上海到北京有多远 | False | **困难负样本：两个地名** |
| 8 | 成都的历史沿革 | False | **困难负样本：有地名** |
| 9 | 你好 | False | 简单负样本 |
| 10 | 推荐几本科幻小说 | False | 简单负样本 |

**关键认知二：困难负样本是实验的核心。** 它们表面特征和天气问题高度相似（都带城市名），能暴露描述质量。简单负样本所有描述都能答对，区分不出差距。

**关键认知三：单变量控制。** 两套 tools 必须只有描述文字不同，`name`、参数名、`required` 逐字一致。

| 字段 | 详细版 | 模糊版 |
|---|---|---|
| `name` | 一样 | 一样 |
| function 描述 | 四要素齐全 | 查询数据 |
| 参数名 | location | location |
| 参数描述 | 城市中文名，不含"市"字，例如… | 输入 |
| `required` | ["location"] | ["location"] |

### 2.5 实验代码

```python
def should_call_tool(question, tools):
    """
    给模型一个问题和一套工具，返回模型是否决定调用工具（True/False）
    这个实验只测「判断」，不测执行，所以不需要解析参数，也不需要执行函数
    """
    # 每个问题都是独立的新对话，不带历史
    messages = [
        {"role": "system", "content": "你是一个助手"},
        {"role": "user", "content": question},          # 用参数，不加引号
    ]

    payload = {
        "model": "deepseek-flash",
        "messages": messages,
        "temperature": 0,                   # 关掉随机性，结果可复现
        "max_tokens": 200,
        "thinking": {"type": "disabled"},
        "tools": tools,                     # 用传进来的那套 tools
    }

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=30)
    except httpx.TimeoutException as e:
        print("超时了:", e)
        sys.exit(1)
    except httpx.RequestError as e:
        print("网络错误:", e)
        sys.exit(1)

    if response.status_code != 200:
        print(response.status_code)
        print(response.text)
        sys.exit(1)

    data = response.json()
    tracker.record("deepseek-flash", data["usage"])    # tracker 在函数外创建，这里只记账

    message = data["choices"][0]["message"]
    return "tool_calls" in message           # 这个表达式本身的值就是 True/False


# 两套 tools 打包：每项是（标签字符串, 已定义的变量）
tool_sets = [("详细版", tools_detailed), ("模糊版", tools_vague)]

for name, tools in tool_sets:                # 外层：遍历两套描述
    correct = 0                              # 每套重新计数
    print(f"\n===== {name} =====")

    for question, expected in test_cases:    # 内层：元组解包，不用下标
        actual = should_call_tool(question, tools)
        if actual == expected:
            correct += 1
        mark = "✅" if actual == expected else "❌"      # 条件表达式：一行的 if/else
        print(f"{mark} {question}  预期:{expected}  实际:{actual}")   # 和 if 同级，每题都打印

    print(f"准确率: {correct}/{len(test_cases)} = {correct / len(test_cases):.0%}")

tracker.report()                             # 所有循环跑完后只报告一次
```

**判断标准：这件事每个问题都要做一遍吗？** 是 → 放函数里；否 → 放函数外。

| 代码 | 每个问题都做吗 | 位置 |
|---|---|---|
| 读 Key、headers、url | 否 | 函数外 |
| `tracker = CostTracker()` | **绝不能每次做** | 函数外 |
| 测试集、循环 | 否，循环是在调用函数 | 函数外 |
| messages、payload、请求 | 是 | 函数内 |
| `tracker.record` | 是 | 函数内 |

### 2.6 第一轮结果：两套都是 100%

**条件**：函数名 `get_weather`，system 为「你是一个天气查询助手」

| # | 问题 | 预期 | 详细版 | 模糊版 |
|---|---|---|---|---|
| 1 | 北京今天多少度 | True | True ✅ | True ✅ |
| 2 | 上海现在天气怎么样 | True | True ✅ | True ✅ |
| 3 | 深圳热不热 | True | True ✅ | True ✅ |
| 4 | 广州现在下雨吗 | True | True ✅ | True ✅ |
| 5 | 杭州要穿外套吗 | True | True ✅ | True ✅ |
| 6 | 北京有哪些好玩的景点 | False | False ✅ | False ✅ |
| 7 | 上海到北京有多远 | False | False ✅ | False ✅ |
| 8 | 成都的历史沿革 | False | False ✅ | False ✅ |
| 9 | 你好 | False | False ✅ | False ✅ |
| 10 | 推荐几本科幻小说 | False | False ✅ | False ✅ |
| | **准确率** | | **10/10** | **10/10** |

成本：20 次调用，输入 6052 token，输出 1193 token，$0.001624

**为什么模糊版没有变差？实验设计没控制干净。** 模糊版虽然描述写成了「查询数据」，但模型还能从另外两个渠道拿到同样的信息：

| 信息渠道 | 详细版 | 模糊版 | 泄露了什么 |
|---|---|---|---|
| description | 四要素齐全 | 查询数据 | — |
| **函数名** | `get_weather` | `get_weather` | **「这是查天气的」** |
| **system** | 天气查询助手 | 天气查询助手 | **「你只管天气」** |

函数名本身就是一句完整的描述，system 又告诉模型它是天气助手。模型根本不需要读 description。

### 2.7 第二轮结果：100% vs 70%

**条件**：函数名改为无含义的 `tool_a`，system 改为「你是一个助手」（两套一致）

| # | 问题 | 预期 | 详细版 | 模糊版 |
|---|---|---|---|---|
| 1 | 北京今天多少度 | True | True ✅ | True ✅ |
| 2 | 上海现在天气怎么样 | True | True ✅ | True ✅ |
| 3 | 深圳热不热 | True | True ✅ | True ✅ |
| 4 | 广州现在下雨吗 | True | True ✅ | True ✅ |
| 5 | 杭州要穿外套吗 | True | True ✅ | True ✅ |
| 6 | 北京有哪些好玩的景点 | False | False ✅ | **True ❌** |
| 7 | 上海到北京有多远 | False | False ✅ | **True ❌** |
| 8 | 成都的历史沿革 | False | False ✅ | **True ❌** |
| 9 | 你好 | False | False ✅ | False ✅ |
| 10 | 推荐几本科幻小说 | False | False ✅ | False ✅ |
| | **准确率** | | **10/10 = 100%** | **7/10 = 70%** |

成本：20 次调用，输入 5992 token，输出 1420 token，$0.001751

### 2.8 按类别汇总

| | 正样本 (5) | 困难负样本 (3) | 简单负样本 (2) | 准确率 |
|---|---|---|---|---|
| 详细版 | 5/5 | 3/3 | 2/2 | **100%** |
| 模糊版 | 5/5 | **0/3** | 2/2 | **70%** |

### 2.9 两轮条件对照

| | 函数名 | system | 详细版 | 模糊版 |
|---|---|---|---|---|
| 第一轮 | get_weather | 天气查询助手 | 100% | 100% |
| 第二轮 | tool_a | 一个助手 | 100% | **70%** |

两轮之间只改了函数名和 system，模糊版就从 100% 掉到 70%。

### 2.10 实验结论

**结论一：描述太宽泛的主要风险是误调，不是漏调。**

模糊版的 3 次错误**全部集中在困难负样本**：把非天气问题误判为需要调用工具。正样本 5 个全对，包括不含「天气」二字的第 3、5 题。

原因：「查询数据」+「输入」这个描述几乎什么问题都能套进去。问题里一出现城市名，模型就认为「这是一个可以查的东西」。详细版靠两句话避免了这一点：「当用户询问气温、天气状况…时」**限定了触发条件**，「不要用于…」**划定了边界**。

**结论二：困难负样本是区分描述质量的关键。**

简单负样本在两种描述下都全部判对。**如果测试集里只有简单负样本，模糊版得分会是 100%，看不出任何区别。**

**结论三：函数名和 system 也是描述的一部分。**

第一轮中它们足以弥补 description 的缺失。实际意义：**函数名起得好，能弥补很大一部分描述上的不足**。`search_product_by_price` 比 `search` 好，`get_weather` 比 `func1` 好。

**结论四：误调不只是判断错误，它还在花钱。**

第二轮输出 token 比第一轮多 227 个（1420 vs 1193），来自模糊版多调的 3 次工具：每次返回 `tool_calls` 都要生成函数名和参数，按输出价计费。在真实 Agent 里，误调还会触发真实的函数执行，成本和风险都会放大。

**局限：样本量太小。**

每类样本只有 2 到 5 条。「3 个困难负样本全错」是清晰的信号，但不能据此说「模糊描述的误调率是 100%」。要下可靠的结论，困难负样本至少要二三十条，并且应该覆盖多种类型（地名、时间词、相关但不相同的领域）。**结论只说到数据支撑得住的地方。**

### 2.11 预测与实际

实验前的预测：模糊版会**漏调**第 3、5 题，也会**误调**困难负样本。

| 预测 | 实际 |
|---|---|
| 漏调第 3、5 题 | **没发生**，正样本全对 |
| 误调困难负样本 | **发生了**，3 题全错 |

第一轮预测还完全错了（没有考虑到函数名和 system 的信息泄露）。**跑出来才算数。**

---

## 第三章 并行调用与多轮工具循环

### 3.1 Agent 循环

```
问模型 → 模型要工具？
          ├── 是 → 执行所有工具 → 结果回填 → 再问模型
          └── 否 → 返回最终回答
```

**模型自己决定调什么、调几次、什么时候停。** 代码只负责这个循环。后面学的 ReAct、各种 Agent 框架，拆开来看都是它。

### 3.2 并行调用：tool_calls 是列表

模型可能一次返回多个调用：

```json
"tool_calls": [
  {"id": "call_00_aaa", "function": {"name": "get_weather", "arguments": "{\"location\": \"北京\"}"}},
  {"id": "call_01_bbb", "function": {"name": "get_weather", "arguments": "{\"location\": \"上海\"}"}}
]
```

**规则：一次请求只产生一条回复，回复里可以装多个调用。**

- assistant 消息：**每轮追加 1 条**（它整条包含了所有调用）
- tool 消息：**每个调用追加 1 条**，各带对应的 `tool_call_id`

```
assistant（tool_calls: [北京, 上海]）    ← 1 条
tool（tool_call_id = call_00_aaa）      ← 北京的结果
tool（tool_call_id = call_01_bbb）      ← 上海的结果
```

两个结果都是「xx℃」，服务器靠 id 才知道哪个是北京、哪个是上海。**这是 `tool_call_id` 真正派上用场的地方。**

> **点菜的比方**：服务员每来一次，你说一句话，一句里可以点好几道菜（1 条 assistant，多个 tool_calls）；每道菜端上来是一次（每个结果一条 tool 消息）；服务员来了三次就是 3 条 assistant。

### 3.3 字典分发

```python
def greet(name):
    return f"你好，{name}"

func_map = {"greet": greet}    # 存的是函数本身，不加括号
f = func_map["greet"]          # 按名字取出函数
print(f("小明"))               # 再调用：你好，小明
```

Python 里函数也是对象，可以当字典的值存。加新工具只需要两步：**写函数、往字典加一项**，分发代码永远不用改。

> 这就是第 1 周写的 `ToolRegistry`。当时还没有大模型来调它，现在它终于有用武之地了。

### 3.4 `**` 解包

```python
args = {"a": 18, "b": 12, "operation": "subtract"}
calculate(**args)
# 等价于 calculate(a=18, b=12, operation="subtract")
```

`**` 只负责**把字典拆成关键字参数**，计算是函数体的事。好处是分发代码不需要知道每个工具有几个参数，都是 `func(**args)` 一行。

**前提：声明里的参数名必须和函数定义完全一致。** 声明写 `location`，函数写 `city`：

```
TypeError: get_weather() got an unexpected keyword argument 'location'
```

### 3.5 必须设轮数上限

不设上限，模型可能陷入「调工具 → 不满意 → 再调 → 再不满意」的死循环。典型场景：工具返回「未找到」，模型换个写法再查，又找不到，再换……每一轮都在花钱。

**上限不是可选项。** 超出时返回明确提示，不要静默结束。

### 3.6 计算工具为什么不用 eval

`eval("18-12")` 最省事，但 `eval` 会执行**任何** Python 代码。模型的输出受用户输入影响，用户在问题里埋一句精心构造的指令，模型可能传过来 `"__import__('os').system('删除文件的命令')"`。

**模型的输出永远不能直接当代码执行。** 安全的设计：参数是两个数字加一个运算类型，运算类型用 `enum` 限定：

```json
"operation": {
    "type": "string",
    "enum": ["add", "subtract", "multiply", "divide"],
    "description": "运算类型，subtract 计算 a - b，divide 计算 a / b"
}
```

### 3.7 JSON Schema 类型名

tools 声明里用的是 JSON Schema 的类型名，**不是 Python 的**：

| JSON Schema（写在 tools 里） | 对应 Python | 说明 |
|---|---|---|
| `"number"` | `int` 或 `float` | 整数小数都接受 |
| `"integer"` | `int` | 只接受整数 |
| `"string"` | `str` | |

写成 `"int"` 是非法的，API 会报错。

### 3.8 工具函数

```python
def get_weather(location):
    """查询城市天气（mock 数据）"""
    weather_data = {"北京": "12℃", "上海": "18℃", "广州": "26℃"}
    if location not in weather_data:
        # 可查城市列表从 weather_data 生成，不要手写第二份
        return f"未查到{location}的天气。目前可查询的城市：{'、'.join(weather_data)}"
    return weather_data[location]                  # 必须 return，print 的话模型看不到


def calculate(a, b, operation):
    """两数四则运算"""
    if operation == "add":
        return a + b
    elif operation == "subtract":
        return a - b
    elif operation == "multiply":
        return a * b
    elif operation == "divide":
        if b == 0:                                 # 先检查，再计算
            return "除数不能为0"
        return a / b
    else:
        return f"不支持的运算类型：{operation}"      # 兜底：enum 降低出错概率，但不保证


# 名字 → 函数的映射表：键和 tools 声明里的 name 一字不差，值是函数本身
tool_map = {"get_weather": get_weather, "calculate": calculate}
```

### 3.9 call_llm 与 run_agent

```python
def call_llm(messages):
    """发一次请求，返回模型的回复 message。不执行任何工具"""
    payload = {
        "model": "deepseek-flash",
        "messages": messages,
        "temperature": 0,
        "max_tokens": 500,
        "thinking": {"type": "disabled"},
        "tools": tools,
    }
    # 异常处理和状态码检查与前面相同，系统级错误直接 sys.exit
    ...
    data = response.json()
    tracker.record("deepseek-flash", data["usage"])
    return data["choices"][0]["message"]


def run_agent(question):
    """Agent 主循环：反复问模型需要什么、给它，直到它给出答案"""
    messages = [
        {"role": "system", "content": "你是一个助手。涉及数学计算时必须使用 calculate 工具，不要自己心算。"},
        {"role": "user", "content": question},
    ]

    for round_num in range(1, 6):                      # 外层：和模型来回交互，最多 5 轮
        message = call_llm(messages)                   # 每轮一次 API 调用
        messages.append(message)                       # 每轮追加一次，在内层循环外

        if "tool_calls" not in message:                # 模型不要工具了
            return message["content"]                  # 正常出口：直接结束整个函数

        for tool_call in message["tool_calls"]:        # 内层：本轮的每个调用
            call_id = tool_call["id"]
            name = tool_call["function"]["name"]       # name 在 function 里面
            raw_args = tool_call["function"]["arguments"]

            # 第四章在这里加了 try/except，见 4.7
            args = json.loads(raw_args)                # loads 读字符串，load 读文件
            result = tool_map[name](**args)            # 按名字找函数，拆开参数执行
            print(f"[第{round_num}轮] {name}({raw_args}) → {result}")

            messages.append({                          # 追加的是 messages（复数）
                "role": "tool",
                "tool_call_id": call_id,
                "content": str(result),                # str 改变类型不改变内容
            })

    return "超出最大轮数，任务未完成"                     # 兜底出口：和外层 for 对齐
```

**三个最容易放错的位置**：

| 代码 | 正确位置 | 放错的后果 |
|---|---|---|
| `messages.append(message)` | 内层 for **外面** | 放进去 → assistant 重复 |
| `if "tool_calls" not in message` | 内层 for **前面** | 放后面 → 遍历空列表，白白进入下一轮 |
| 兜底 return | 和外层 for **对齐** | 缩进进循环 → 第一轮没结束就返回 |

**`return` 和 `break` 的区别**：`return` 直接结束整个函数，外层循环剩下的轮次、底下的兜底 return 都不会执行；`break` 只跳出当前一层循环，函数还会继续往下走。

### 3.10 run_agent 是引擎，不是展示

| 部分 | 它做什么 | 它不做什么 |
|---|---|---|
| `get_weather`、`calculate` | 被调用时执行一次 | 不知道自己什么时候该被调用 |
| `tools` 声明 | 告诉模型有哪些工具 | 不执行任何东西 |
| `tool_map` | 按名字查到函数 | 只是查找表 |
| `call_llm` | 问模型一次 | **不执行任何工具** |
| **`run_agent`** | **把上面这些串起来** | — |

去掉 `run_agent`，零件就只是放在那里，谁也不会动。**展示用的只有那一行 print**，删掉它 Agent 行为完全不变，调用次数也不变。

**和第 1 节的关系**：第 1 节写死了两次请求，只能处理「刚好调一次工具」。`run_agent` 把手动步骤放进循环，能处理任意轮次。**第 1 节是手动挡，`run_agent` 是自动挡。**

### 3.11 API 调用 vs 本地执行

| | API 调用 | 执行工具 |
|---|---|---|
| 是什么 | 发请求给 DeepSeek | 你电脑上跑一个 Python 函数 |
| 花钱吗 | 是 | 否（除非工具本身调付费服务） |
| 速度 | 要等网络和模型 | 几乎瞬间 |

「北京和上海温差多少度」的完整计数：

| 轮次 | API 调用 | 模型返回 | 本地执行 |
|---|---|---|---|
| 1 | 第 1 次 | 2 个 get_weather（并行） | 两次 get_weather |
| 2 | 第 2 次 | 1 个 calculate | 一次 calculate |
| 3 | 第 3 次 | 最终回答 | — |

**3 次 API 调用。** 北京和上海是同一轮并行查的；「把结果告诉用户」只是 print，不是 API 调用。

### 3.12 实测结果

**执行轨迹**：

```
[第1轮] get_weather({'location': '北京'}) → 12℃
[第1轮] get_weather({'location': '上海'}) → 18℃
今天两地的天气情况：
- **北京**：12°C
- **上海**：18°C
上海比北京暖和一些，温差 6°C。工具只返回了气温，没有降雨、风力等信息，如果需要更详细的天气状况，可以再告诉我。

[第1轮] get_weather({'location': '北京'}) → 12℃
[第1轮] get_weather({'location': '上海'}) → 18℃
[第2轮] calculate({'a': 18, 'b': 12, 'operation': 'subtract'}) → 6
北京当前气温 12°C，上海当前气温 18°C，两地温差为 **6°C**（上海比北京高 6°C）。

你好！有什么可以帮你的吗？比如查天气、做计算，都可以告诉我。
```

（这一版打印的是解析后的字典，所以是单引号；第四章改为打印原始字符串 `raw_args` 后变成双引号）

| 问题 | 预期轨迹 | 实际 |
|---|---|---|
| 天气怎么样 | 1 轮，两次 get_weather 并行 | ✅ |
| 温差多少度 | 3 轮：并行查询 → calculate → 回答 | ✅ |
| 你好 | 无工具调用 | ✅ |

**「温差」那题结束时的 messages**：

| # | role | 内容 |
|---|---|---|
| 1 | system | 你是一个助手…… |
| 2 | user | 北京和上海温差多少度 |
| 3 | assistant | tool_calls：get_weather(北京)、get_weather(上海) |
| 4 | tool | 12℃ |
| 5 | tool | 18℃ |
| 6 | assistant | tool_calls：calculate(18, 12, subtract) |
| 7 | tool | 6 |
| 8 | assistant | 北京比上海低 6℃ |

**这张表就是 Agent 的完整工作记录。** 第 2 轮模型之所以知道两个温度，是因为每次 `call_llm` 都发送**完整的** messages，这就是第 4 周「API 无状态，记忆靠你维护数组」。

**成本**：

| 指标 | 数值 |
|---|---|
| API 调用 | 6 次（2 + 3 + 1） |
| 输入 token | 3290 |
| 输出 token | 310 |
| 输入 : 输出 | 约 **10 : 1** |
| 花费 | $0.000679 |

**Agent 的钱几乎都花在输入上。** 每一轮都要重发 tools 声明和完整历史，轮次越多输入越膨胀。

### 3.13 实测中的四个观察

**观察一：prompt 里的「必须」是软约束。**

第一题用户没问温差，模型**顺手补充**了「温差 6°C」，这个 6 是它**心算**的，没调 calculate。而 system 明明写了「必须使用 calculate，不要自己心算」。

模型大概判断这是附带的一句话，不算「数学计算任务」。18 减 12 心算不会错，但如果换成金额计算、库存扣减，一旦算错就是真实损失。**真正不能出错的规则，要靠代码保证，不能只靠 prompt 嘱咐。**

**观察二：参数顺序对了。** 模型把 18 放在 a、12 放在 b，得到正数 6。这得益于参数描述里写了「被减数 / 减数」。

**观察三：模型知道自己的能力。** 「你好」没有调用任何工具，但回答里提到「查天气、做计算」，从 tools 声明里知道的。

**观察四：输出里有 `**` 和 `-`。** 模型默认用 Markdown 排版，网页聊天界面会渲染，终端只能显示原始符号。纯文本场景可以在 system 里要求「不要使用 Markdown 格式」。

---

## 第四章 错误处理与结果回填

### 4.1 工具失败的三种情况

| 类型 | 例子 | 未处理时 |
|---|---|---|
| **业务失败** | 查不到城市；除数为 0 | ✅ 函数 return 一句提示，模型能看到 |
| **执行异常** | 参数名对不上 → `TypeError`；参数是「十八」 → 运算时 `TypeError` | ❌ **整个程序崩溃** |
| **调用无效** | 工具名不存在 → `KeyError`；arguments 不是合法 JSON → `JSONDecodeError` | ❌ **整个程序崩溃** |

### 4.2 核心做法：错误也是一种工具结果

```
执行工具
  ├── 成功 → 结果回填
  └── 失败 → 错误信息写成字符串，同样作为结果回填
```

模型读到错误信息后，通常会换参数重试、换工具，或者告诉用户做不到。这就是 Agent 的**自我修正**，前提是**你把错误告诉了它**。程序崩掉，模型连修正的机会都没有。

### 4.3 为什么不能跳过出错的调用

API 硬性规定：**assistant 消息里的每一个 `tool_call_id`，后面都必须有一条对应的 tool 消息。** 少一条，下一次请求在格式检查时就会被服务器拒绝（400），模型根本没机会思考。

所以不管成功还是失败，**每个调用都必须回填**。

### 4.4 错误信息写给模型看

| 写法 | 模型的后续行为 |
|---|---|
| 「出错了」 | 不知道原因，很可能换个说法再查，又失败 |
| 「未查到深圳。可查询：北京、上海、广州」 | 知道原因和选择，直接告诉用户深圳查不到、支持哪些城市 |

但**不要把内部细节原样暴露**：完整堆栈、文件路径、密钥片段。模型的回答最终会给用户看。

### 4.5 哪些回填，哪些直接停

| 错误来源 | 例子 | 模型能修吗 | 处理 |
|---|---|---|---|
| **工具层** | 参数不对、城市不存在、工具名错 | 有可能 | **回填给模型** |
| **系统层** | 401、402、网络断 | 不可能 | **直接停** |

401 不能回填，有个很硬的理由：**401 本身就是「调用模型」失败了**。Key 错了连模型都联系不上，传话的通道本身就断了。`call_llm` 里的 `sys.exit` 处理的就是这一类。

### 4.6 except Exception 的风险

假设工具里手滑写错变量名：

```python
reslut = a + b        # 拼错了
return result         # NameError
```

没有兜底，程序当场崩溃，你立刻知道有 bug。有了 `except Exception`，这个 `NameError` 被悄悄接住，变成「工具执行失败」回填给模型，模型礼貌地告诉用户「计算失败了」。**程序看起来运行正常，你可能好几天都发现不了。**

**弥补：两个读者，两份信息。**

- 给模型：简短说明「工具执行失败」
- 给开发者：完整的异常类型和信息，print 到终端

### 4.7 最终的内层循环

```python
for tool_call in message["tool_calls"]:
    # 放在 try 外面：不管成功失败，回填和打印都要用
    call_id = tool_call["id"]
    name = tool_call["function"]["name"]
    raw_args = tool_call["function"]["arguments"]      # 原始字符串，日志用它，永远是模型真正传的

    try:
        if name not in tool_map:                       # 调用无效：工具不存在
            result = f"错误：不存在名为 {name} 的工具"
        else:
            args = json.loads(raw_args)
            result = tool_map[name](**args)
    except json.JSONDecodeError:                       # 具体的放前面
        result = "错误：参数不是合法的 JSON"
    except TypeError as e:
        result = f"错误：参数不正确（{e}）"
    except Exception as e:                             # 最宽泛的兜底放最后
        # 给开发者看：异常类型名能最快判断是哪类 bug
        print(f"[开发者日志] 工具 {name} 发生未预期的异常：{type(e).__name__}: {e}")
        result = f"错误：工具执行失败（{e}）"

    print(f"[第{round_num}轮] {name}({raw_args}) → {result}")

    messages.append({                                  # 在 try/except 之后：成功失败都回填
        "role": "tool",
        "tool_call_id": call_id,
        "content": str(result),
    })
```

### 4.8 故障注入测试

正常情况下模型很少出错，所以要**主动注入故障**，每次只注入一个，测完恢复。

**测试 ①：业务失败（深圳）**

第一次运行：

```
[第1轮] get_weather({'location': '深圳'}) → 未查到该城市的天气,只可以查询以下城市的天气['北京','上海']
最终回答：抱歉，目前天气查询只支持北京和上海两个城市，查不到深圳的天气。……
```

模型没有重试，回答里也提到了可查询城市，说明它读懂了错误信息。**但广州去哪了？** `weather_data` 里明明有三个城市。

可查城市列表是手写的，和 `weather_data` 是两份独立数据，写漏了。**模型没有犯错，它只是原样相信了工具告诉它的东西。**

改为从 `weather_data` 生成列表后：

```
[第1轮] get_weather({'location': '深圳'}) → 未查到该城市的天气,只可以查询以下城市的天气['北京','上海','广州']
最终回答：抱歉，目前天气查询只支持北京、上海、广州三个城市，查不到深圳的天气。……
```

**改了一处工具输出，模型的回答就跟着变准确了。**

**测试 ②：工具不存在**

在 tools 里临时加入 `get_air_quality` 的声明，但不放进 `tool_map`。

```
[第1轮] get_air_quality({"location": "北京"}) → 错误：不存在名为get_air_quality的工具
最终回答：抱歉，我这边查询空气质量的功能暂时不可用（工具调用报错），所以没法给出北京当前的空气质量数据。
你可以试试：打开手机天气 App 或天气网站查看实时 AQI；或者告诉我你想了解北京的天气……
```

程序没有崩，模型只调一次就放弃，没有重试，并给出替代建议。这就是**优雅降级**：做不到的事坦白说，然后给出能做的选项。

> **日志的教训**：第一次运行时这一行显示的是 `get_air_quality({})`，看起来像模型没传参数。实际是代码在 try 前写了 `args = {}`，而这条路径没执行 `json.loads`，打印的是初始值。改为打印原始字符串 `raw_args` 后，显示出模型真正传的 `{"location": "北京"}`。**一条显示错误信息的日志比没有日志更麻烦，因为你会相信它。**
>
> **这个故障在真实项目里很常见**：声明写了，函数没写（或改了名，声明没跟着改）。根源是 tools 声明和 tool_map 是两份分开维护的数据。成熟的做法是只维护一份：注册函数时自动生成声明。

**测试 ③：参数名不匹配**

临时把 `get_weather` 的参数改成 `city`，声明不改。

```
[第1轮] get_weather({'location': '北京'}) → 错误：参数不正确（get_weather() got an unexpected keyword argument 'location'）
[第2轮] get_weather({'location': '北京'}) → 错误：参数不正确（get_weather() got an unexpected keyword argument 'location'）
最终回答：抱歉，天气查询工具目前报错，我暂时无法获取北京的实时气温。你可以稍后再试，或者告诉我其他城市，我再帮你查一次。
```

3 次 API 调用，没有撞到 5 轮上限。但有两个问题：

- **第 2 轮是白花钱**：参数和第 1 轮一字不差，结果当然一样
- **最终回答误导了用户**：「稍后再试」没用，这是代码 bug 不是临时故障；「换个城市」也没用，bug 在函数签名上，查哪个城市都会报错

**模型把永久性的代码错误当成了临时故障。**

**测试 ④：工具内部 bug**

在 `get_weather` 函数体里临时写一个未定义的变量，触发 `NameError`，用于验证 `except Exception` 分支和开发者日志。

### 4.9 三次测试的对比

| 测试 | 错误信息 | 模型是否重试 |
|---|---|---|
| ① | 未查到深圳，可查询：北京、上海、广州 | 否 |
| ② | 不存在名为 get_air_quality 的工具 | 否 |
| ③ | 参数不正确（…unexpected keyword argument 'location'） | **是** |

**错误信息的措辞直接影响模型的决策。** 「参数不正确」听起来像模型自己传错了，所以它觉得值得再试。但它检查发现自己传的就是声明要求的 `location`，没有可改的，只好原样再发一次，然后放弃。

### 4.10 TypeError 的两种来源

| 来源 | 例子 | 谁的错 | 重试有用吗 |
|---|---|---|---|
| 模型传错参数 | 声明是 location，模型自己编了个 city | 模型 | **有用**，告诉它正确参数名 |
| 函数和声明不一致 | 声明是 location，函数写成 city | 你 | **没用** |

目前两种都写成「参数不正确」，模型分不清。

**改进方向**（本周未实现）：调用函数前，先拿模型传的参数和声明比对。对不上 → 模型的错，告诉它应该传哪些参数；对得上但函数仍报 TypeError → 你的错，告诉模型「工具内部错误，重试无效」，同时打印日志。

**错误信息除了说「错在哪」，最好还要说「重试有没有用」。**

### 4.11 回填不能解决所有错误

| 错误类型 | 回填能做到的 |
|---|---|
| 模型能修的（传错城市、参数格式） | 模型换参数重试，任务完成 |
| 模型修不了的（你代码里的 bug） | 程序不崩，模型体面地告诉用户失败了。**修 bug 还是得靠你看日志** |

---

## 第五章 概念补课

### 5.1 Tokenizer：文本怎么变成数字

```
"北京今天多少度"
→ 切分：["北京", "今天", "多少", "度"]
→ 编号：[3821, 1029, 2290, 518]      ← 示意值
```

主流方法 **BPE（Byte Pair Encoding）**：

1. 一开始，每个字符是一个片段
2. 统计海量文本里哪两个相邻片段最常一起出现，合并成新片段
3. 重复几万次，得到词表

所以常见词合并成一个 token，生僻组合被拆开；**不同模型用不同语料训练出不同词表，同一句话 token 数不同**。

### 5.2 Embedding：编号怎么变成含义

每个 token 编号查表得到一串数字（向量）：

```
"猫"   → [0.21, -0.53, 0.88, 0.07, ...]
"狗"   → [0.19, -0.48, 0.91, 0.12, ...]
"汽车" → [-0.72, 0.33, -0.15, 0.64, ...]
```

**意思相近的词，向量也相近。** 这些向量不是人工设计的，是从海量文本里自动学出来的，依据是**两个词经常出现在相似的上下文里**：「喂猫」「喂狗」、「猫叫了」「狗叫了」。相似度高，说明两个词在语言里的**用法相近**。

**余弦相似度**：看两个向量的夹角。

```
cos θ = (A · B) / (|A| × |B|)
```

结果 1 方向相同，0 毫无关系，-1 方向相反。

> 通信视角：这和**两个信号的归一化相关系数**是同一个式子。

**两种 embedding**：

| | Token embedding | 文本 embedding |
|---|---|---|
| 给谁用 | 大模型内部第一层 | **RAG 检索** |
| 粒度 | 每个 token 一个向量 | **一整段话一个向量** |
| 接触到吗 | 不直接接触 | **第 6 周就会用** |

### 5.3 Embedding 检索 vs 关键词搜索

```
用户问题：北京冷不冷？
文档 A：北京今日气温零下 3℃，有大风
文档 B：冷冻食品的储存方法
```

- **关键词搜索**选 B：它包含「冷」字，A 里一个「冷」字都没有
- **embedding 检索**选 A：「冷不冷」和「零下 3℃」意思相近，向量也相近

**意思相近的文本向量相近。把问题和文档都变成向量，找余弦相似度最高的几段，就能找到意思最相关的文档，即使用词完全不同。**

关键词搜索也不是没用：专有名词、型号、人名，embedding 有时反而不如关键词准。实践中常把两者结合（混合检索）。

### 5.4 Transformer：自注意力

```
小明把苹果给了小红，因为她饿了。
```

「她」的向量是固定的，指谁要看上下文。

**自注意力：处理「她」时，同时计算它对句子里每一个 token 的关注度，一次得出所有权重，然后按权重把各 token 的信息加权混合进「她」的向量。**

```
小明 0.15 ｜ 苹果 0.05 ｜ 小红 0.70 ｜ 饿了 0.10     ← 示意值
```

三个关键词：**同时看所有、按相关度分配权重、加权混合**。不是依次扫描。权重分配的规律是训练中从大量类似句子里学到的。

### 5.5 生成：一次一个 token

模型训练时只学一件事：**给定前面的内容，预测下一个 token。** 生成就是反复做这件事，每次输出的是**词表里每个 token 的概率**，然后从中挑一个。

**这个机制解释了前五周的现象**：

| 现象 | 原因 |
|---|---|
| 流式输出逐字蹦出 | 模型本来就一次生成一个 token，流式只是生成一个发一个 |
| temperature 控制随机性 | 调的是「从概率分布里怎么挑」 |
| TTFT 占总耗时 77% | 生成第一个字前，要先把整个输入读一遍，算所有 token 之间的注意力 |
| **输出比输入贵 4 倍** | 输入所有 token 已知，可**并行**一次算完；输出只能**串行**，每生成一个都要跑一遍模型 |
| 缓存命中便宜 50 倍 | 读输入时算出的中间结果可以存下来，开头相同就直接复用 |
| 上下文越长越贵越慢 | 每个 token 都要看所有其他 token，长度翻倍计算量约翻四倍 |

> **生成方式和 SSE 无关。** 不开流式时模型也是一个一个生成的，只是生成完再一次性发回。第 4 周验证过：流式和非流式计费完全一样。

### 5.6 幻觉

**根源**：模型被训练成生成**流畅**的文本，而不是**正确**的文本。它知道答案时，最可能的下一个 token 往往就是正确的；不知道时，它**没有「我不知道」的开关**，依然输出概率最高的那串，读起来同样流畅自信。

**三个常见误解**：

| 误解 | 纠正 |
|---|---|
| temperature 设成 0 就不会幻觉 | 0 只让输出**确定**，不让输出**正确**。它可能**稳定地错** |
| 更强的模型就不会幻觉 | 能减少不能消除。知识有截止时间，私有数据它从没见过 |
| 模型说错了就是幻觉 | 第四章的「广州」不是幻觉，它忠实转述了工具的错误输出。这叫**垃圾进，垃圾出** |

**对抗方法**：

| 方法 | 原理 | 在哪里用过 |
|---|---|---|
| 明确允许「不知道」 | prompt 里规定找不到填 null | 第 4 周简历抽取 |
| 给它真实数据 | 把事实塞进上下文 | 第 4 周把当前日期写进 system |
| 让它调工具 | 实时数据通过工具获取 | 第 5 周整周 |
| **RAG** | 先检索相关文档，再基于文档回答 | **第 6 周** |

**RAG 本质上是「给它真实数据」的规模化版本**：不可能把整个知识库塞进 prompt，所以先用 embedding 找出最相关的几段。

---

## 第六章 典型错误合集

> ⚠️ **本章所有标记 ❌ 的代码都是错误示范，请勿复制使用。**
> 按根因分类而非时间顺序。

### 根因一：数据结构的层级与类型（本周最高频）

---

**错误 1：对字符串调用 `.json()`**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
arguments = data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
arguments_json = arguments.json()      # 字符串没有 .json() 方法
```

报错：`AttributeError: 'str' object has no attribute 'json'`

**原因**：`.json()` 是 httpx **响应对象**专属的方法。拆开之后拿到的字典、字符串都是普通数据，没有这个方法。

**✅ 正确做法**：

```python
arguments_json = json.loads(arguments)
```

| 写法 | 作用对象 |
|---|---|
| `response.json()` | httpx 的响应对象 |
| `json.loads(字符串)` | 任何 JSON 格式的字符串 |

> **这是同一类混淆的第三次**：第 4 周写过 `response["choices"]`（把响应对象当字典），这次把字符串当响应对象。根源是没分清「响应对象身上挂着方法，数据身上只有数据」。**`.json()` 全程只能按一次，就是在 response 上那次。**

---

**错误 2：messages 多了一层方括号**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
messages = [
    [{"role": "system", ...},
     {"role": "user", ...}],      # ← 旧的方括号没删
]
```

报错：

```
422
{"error":{"message":"Failed to deserialize the JSON body into the target type: messages[0][0]: invalid type: map, expected variant identifier ..."}}
```

**读报错**：`messages[0][0]` 两层下标，说明 `messages[0]` 本身是个列表。**这次 422 发生在第一次请求，状态码检查直接退出，四行解析结果一行都没打印**，没有带着错误继续浪费请求。

PyCharm 在 `messages.append` 下面画了波浪线：它推断出 messages 是「列表的列表」，往里塞字典类型对不上。

---

**错误 3：tools 少了一层方括号**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
tools_detailed = {               # ← 最外层成了花括号
    "type": "function",
    ...
}
```

报错：

```
422
{"error":{"message":"Failed to deserialize the JSON body into the target type: tools: invalid type: map, expected a sequence ..."}}
```

**原因**：把内容挪进 tool_sets 又挪回来的过程中，最外层的 `[` `]` 被删了。

| | 报错路径 | 原因 |
|---|---|---|
| 错误 2 | `messages[0][0]` | 多了一层 `[ ]` |
| 错误 3 | `tools: map, expected sequence` | 少了一层 `[ ]` |

**两次都是 422，两次报错都精确指出了是哪个字段、哪一层。** 看到 422，先读字段名和类型描述，对照自己的结构数括号层级。不确定时 `print(type(tools_detailed))`，应为 `<class 'list'>`。

---

**错误 4：用 `"tool_call_id"` 判断有没有工具调用（静默错误）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
if "tool_call_id" in message:     # 这个键永远不会出现在模型返回的 message 里
    return True
else:
    return False
```

**后果比报错更糟**：判断恒为 False。如果没被发现就直接跑实验，程序会正常跑完、不报任何错，5 个正样本全判错、5 个负样本全判对，**两套描述都是 50%**，得出「描述好坏没有区别」的错误结论。（这次在跑实验前就改掉了）

**✅ 正确做法**：

```python
return "tool_calls" in message
```

> **静默错误最危险**，因为它不会让你停下来检查。这也是为什么要先单独测两行（「北京今天多少度」应为 True）再套循环。

---

**错误 5：tool_map 写成了列表**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
tool_map = [get_weather, calculate]
```

报错：`TypeError: list indices must be integers or slices, not str`

**✅ 正确做法**：按名字查找需要字典。

```python
tool_map = {"get_weather": get_weather, "calculate": calculate}
```

**方括号取值的三种报错**：

| 报错 | 含义 | 典型写法 |
|---|---|---|
| `KeyError` | 字典里没有这个键 | `usage["prompt"]` |
| `IndexError` | 列表下标越界 | 空 `choices` 取 `[0]` |
| `TypeError: list indices must be integers` | 对列表用了字符串下标 | `tool_map["calculate"]` |

---

**错误 6：run_agent 里取值的层级和键名**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
name = tool_call["name"]                       # 少了一层 function
args = json.load(tool_call["arguments"])       # 少了 s，也少了一层 function
call_id = tool_call["call_id"]                 # 键名是 id
```

**✅ 正确做法**：

```python
name = tool_call["function"]["name"]
args = json.loads(tool_call["function"]["arguments"])
call_id = tool_call["id"]
```

```
tool_call
├── "id"
├── "type"
└── "function"
    ├── "name"
    └── "arguments"
```

> 第 1 节检验题刚讲过 `load` 读文件、`loads` 读字符串；`call_id` 是自己起的变量名，键名要照抄响应。**变量名随你起，方括号里的键名必须照抄。**

---

**错误 7：JSON Schema 类型写成 Python 类型名**

```json
// ❌❌❌ 错误示范，请勿复制 ❌❌❌
"a": {"type": "int", "description": "数据"}
```

**✅ 正确做法**：`"number"`（整数小数都接受）或 `"integer"`。

---

**错误 8：工具函数返回列表而不是字符串**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def get_weather(location):
    temperature = ["12℃，晴"]      # 方括号让它变成了列表
    return temperature
```

**原因**：回填时 `content` 必须是字符串。另外函数内的变量名 `temperature` 和 payload 里控制随机性的参数重名，作用域不同不冲突，但读代码时容易混。

---

### 根因二：函数职责与作用域

---

**错误 9：整个脚本塞进了函数里**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def should_call_tool(question, tools):
    test_cases = [...]                  # 定义一次的东西
    for cases in test_cases:            # 循环是调用方的事
        question = cases[0]             # 覆盖了参数 question
        messages = [...]
    payload = {...}
    load_dotenv()                       # 每次调用都重新读 .env
    key = os.getenv(...)
    headers = {...}
    tracker = CostTracker()             # 每次调用都新建 tracker
    ...
    name = data[...]["tool_calls"][0]...   # 负样本时 KeyError
    ...
    return tool_call_id, message
    tracker.report()                    # return 之后的死代码
```

**一个根源，五个后果**：

| 问题 | 后果 |
|---|---|
| 函数里套了 for 循环，覆盖参数 | 不管传什么问题，每次都会发「推荐几本科幻小说」 |
| `tracker = CostTracker()` 在函数里 | 计数器每次归零，函数结束就被丢弃 |
| 无条件取 tool_calls | 负样本必崩 |
| 返回 `tool_call_id, message` | 外层要的是 True/False |
| `report()` 在 return 后 | 永远不会执行，PyCharm 显示为灰色 |

**PyCharm 的提示**：参数 `question` 是**灰色**（传进来从没被用过，被覆盖了），`"messages": messages` 有**黄色波浪线**（定义在循环里，可能不存在）。

**判断标准**：这件事每个问题都要做一遍吗？

**职责**：函数像检票员，每次接一张票检一张；排队的人流在外面，检票员不该自己跑进队伍里拉人。

---

**错误 10：tracker 被实例化两次（本周重犯）**

第 1 节复制第二次请求的代码时，把 `tracker = CostTracker()` 也复制了：

```
总调用次数： 1    总输入 295    总输出 38     ← 两份报告，各自只有 1 次
总调用次数： 1    总输入 351    总输出 8
```

**✅ 正确结果**应为一份报告、2 次调用、646 输入、46 输出。

**每执行一次 `CostTracker()` 就造一个全新对象**，`__init__` 把计数器归零。第 2 节错误 9 里又出现了一次同样的问题（在函数里创建）。

---

**错误 11：工具用 print 而不是 return**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def get_weather(location):
    weather_data = {...}
    if location not in weather_data:
        print("未查到该城市的天气")      # 打印到终端，模型看不到
    # 查到的情况什么都没返回 → None
```

**工具的结果要回填给模型**，必须 `return`。这和第 1 周反复出现的「记录日志不等于中断执行」是同一类：**打印不等于返回**。

---

**错误 12：参数写死，返回值没接住**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
location = arguments_json["location"]     # 辛苦解析出来
get_weather("北京")                        # 却写死了，返回值也没存
```

**后果**：换个城市问，函数还是返回北京的天气，整个解析流程形同虚设。

**✅ 正确做法**：`weather = get_weather(location)`。传 location，用变量接住返回值。

---

**错误 13：变量名遮蔽内置函数**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
id = data["choices"][0]["message"]["tool_calls"][0]["id"]
```

Python 自带 `id()` 函数，这之后就调不了它了。同类的还有 `list`、`dict`、`str`、`type`、`sum`、`input`。改成 `tool_call_id`，正好和回填字段名一致。

---

### 根因三：控制流与分支完整性

---

**错误 14：无条件假设一定有 tool_calls**

问「你好」时：

```
Traceback (most recent call last):
  File "...function_call.py", line 84, in <module>
    name = data["choices"][0]["message"]["tool_calls"][0]["function"]["name"]
KeyError: 'tool_calls'
```

**这不是 bug，是缺一个分支。** 真实 Agent 面对的输入是混合的，必须先判断再解析：

```python
if "tool_calls" in message:
    # 走工具流程
else:
    # 直接取 content
```

---

**错误 15：messages 在循环外，循环变量保留最后一轮的值（重犯）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
for cases in test_cases:
    content = cases[0]           # 循环体只有这一行

messages = [                     # ← 没缩进，在循环外
    {"role": "system", ...},
    {"role": "user", "content": "content"},    # ← 还加了引号，是字面字符串
]
```

两个错：循环跑 10 圈只是给 `content` 赋值，结束时停在最后一条；`"content"` 带引号是字面字符串，模型收到的问题就是 content 这七个字母（和第 4 周 `"Bearer key"` 同一个错）。

> **第 3 周「多发一个"考"」是同一个模式**：循环变量在循环结束后保留最后一轮的值。

---

**错误 16：单等号做比较**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
if real = test[1]:
```

`SyntaxError`。一个等号是赋值，两个等号是比较，`if` 后面只能放判断。

---

**错误 17：print 在 if 里，错题不打印**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
if real == test[1]:
    true_number += 1
    print("问题:", test[0], "预期:", test[1], "实际：", true_number)    # 在 if 里；打印的还是计数
```

三个问题：

- **只有判对才打印，而判错的题恰恰是实验最想看的**
- 「实际」打印的是计数器 `true_number`，不是本题结果 `real`
- 准确率写死 `/ 10`，加第 11 题就算错且不报错，应为 `len(test_cases)`

---

**错误 18：calculate 缺 else 分支（PyCharm 警告）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def calculate(a, b, operation):
    if operation == "add":
        return a + b
    elif operation == "subtract":
        return a - b
    elif ...
    # 四个都不匹配 → 返回 None
```

PyCharm 在 `if` 下画波浪线：「缺少 return 语句」。模型传了 `"减法"` 这类值时，函数返回 None。

**✅ 补一个 else**，返回「不支持的运算类型」。

---

**错误 19：除法先算后判断**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
elif operation == "divide":
    result = a / b       # b 为 0 时这一行就崩了
    if b == 0:           # 永远走不到
        return "除数不能为0"
```

**✅ 正确做法**：先检查 b，再计算。和第 4 周解析 SSE 时「先判断空行再 replace」是同一条规则：**先过滤，再处理**。

---

**错误 20：args 在异常路径下未定义**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
try:
    if name not in tool_map:
        result = "错误：不存在..."      # 这条路径 args 从未赋值
    else:
        args = json.loads(...)
        ...
except ...:
    ...

print(f"[第{round_num}轮] {name}({args}) → {result}")    # NameError
```

PyCharm 在 `args` 下画波浪线：「可能在赋值前被引用」。**辛辛苦苦接住的错误，在打印那一行又崩了。**

> **第 4 周同一个模式**：except 接住了超时，后面却用到没赋值的 `response`。

**初次修复的副作用**：在 try 前写 `args = {}`，不崩了，但日志显示 `get_air_quality({})`，看起来像模型没传参数。

**✅ 最终做法**：打印原始字符串 `raw_args`，它在 try 外就存在，永远是模型真正传的内容。

---

**错误 21：print 只写了函数名**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
except Exception as e:
    print                      # 没有括号，什么都不会发生
    result = ...
```

PyCharm 提示「语句没有任何效果」。兜底分支的开发者日志恰恰是这里最重要的东西。

---

### 根因四：调用与参数传递

---

**错误 22：字符串当函数调用**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def calculate(a, b, operation):
    result = operation(a, b)      # operation 是 "subtract" 这样的字符串
```

报错：`TypeError: 'str' object is not callable`

**✅ 正确做法**：根据字符串的值决定做哪种运算（if/elif）。

---

**错误 23：run_agent 里的三处调用错误**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
messages = [system, user]                  # 这两个名字不存在（红线）
result = tool_map[name](args)              # 少了 **，整个字典被当成一个参数
message.append(result)                     # 单数 message 是字典没有 append；追加的也不是完整的 tool 消息
```

**✅ 正确做法**：

```python
messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": question},
]
result = tool_map[name](**args)
messages.append({"role": "tool", "tool_call_id": call_id, "content": str(result)})
```

不加 `**` 的后果：`get_weather` 收到的 location 是整个字典，查不到；`calculate` 要三个参数只收到一个，直接报错。

---

### 根因五：工具声明与实验设计

---

**错误 24：在 user prompt 里提「工具」**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
{"role": "user", "content": "我要查询北京今天的温度，需要调用哪些工具？"}
```

问题从「帮我查天气」变成了「介绍一下你的工具」，模型可能用文字描述而不返回 `tool_calls`，**破坏了实验**：想验证的是模型能否自主判断，结果变成了能否描述工具。

---

**错误 25：模糊版漏了 parameters 整块**

两套 tools 的差异变成两处（描述质量 + 有没有参数声明），**破坏单变量控制**。准确率有差异时分不清是哪个因素造成的。

---

**错误 26：tool_sets 把 tools 内容又抄了一遍**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
tool_sets = [
    (tools_detailed, [ ...整套工具定义又复制了一遍... ]),
    (tools_vague, [ ...同上... ]),
]
```

两个问题：第一个位置应该是标签字符串而不是变量；内容抄了一份，以后改描述要改两处。

**✅ 正确做法**：

```python
tool_sets = [("详细版", tools_detailed), ("模糊版", tools_vague)]
```

---

**错误 27：calculate 声明缺了 operation 参数**

`properties` 里只有 a 和 b。模型不知道还有 operation，永远不会传它。补上并加 `enum` 和 `required`。

**参数描述写「数据」的风险**：减法和除法有顺序，模型可能传 `a=12, b=18` 得到 -6。描述里写清楚「被减数 / 减数」。

---

**错误 28：可查城市列表手写（双数据源）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
weather_data = {"北京": "12℃", "上海": "18℃", "广州": "26℃"}
...
return "未查到该城市的天气,只可以查询以下城市的天气['北京','上海']"    # 漏了广州
```

模型照实告诉用户「只支持北京和上海」。**模型对工具返回的内容几乎是完全信任的**，工具输出错了，错误会原样传递给用户。

**✅ 从 weather_data 生成**：`"、".join(weather_data)`

> 本周「一份数据只应该有一个来源」出现了四次：不复制 cost_tracker.py、tool_sets 不抄 tools、城市列表不手写、tools 声明和 tool_map 最好从同一个注册表生成。

---

### 错误统计

| 根因分类 | 次数 |
|---|---|
| 数据结构的层级与类型 | 8 |
| 函数职责与作用域 | 5 |
| 控制流与分支完整性 | 8 |
| 调用与参数传递 | 2 |
| 工具声明与实验设计 | 5 |

**重犯的错误**：

| 错误模式 | 本周 | 之前 |
|---|---|---|
| 对象和数据混淆（`.json()`） | 错误 1 | 第 4 周 `response["choices"]` |
| 循环变量保留最后一轮的值 | 错误 15 | 第 3 周多发一个「考」 |
| except 后用到未赋值变量 | 错误 20 | 第 4 周 `response` 未定义 |
| tracker 多次实例化 | 错误 9、10 | 本周内两次 |
| 打印不等于返回 | 错误 11 | 第 1 周「记录 ≠ 中断」 |

**本周最该记住的三条**：

1. **取值前先确认数据结构。** `type()` 看是字典还是列表，`.keys()` 看有哪些键，响应结构不确定就先完整打印一遍。本周 8 个错误来自这里
2. **静默错误比报错更危险。** `tool_call_id` 判断恒为 False 不报任何错，却会让实验得出错误结论；`except Exception` 会把你的 bug 藏起来。**先单独测关键函数，兜底分支一定打日志**
3. **一份数据只应该有一个来源。** 写两遍的东西迟早会对不上

---

## 第七章 本周自检

- [x] 能说清「模型不执行函数，执行的是你的代码」
- [x] 能解释为什么官网能直接回答实时问题而裸 API 不能
- [x] 能写出完整的 tools 声明，知道它放在 payload 顶层
- [x] 能区分 `tool_calls`、`tool_calls[i]["id"]`、`tool_call_id` 三者的方向
- [x] 知道 DeepSeek 返回的 content 是空字符串而不是 null，以及该怎么判断
- [x] 能说清回填时为什么要把 assistant 那条原样发回去
- [x] 理解可变对象的引用，知道两种 append 写法等价
- [x] 能说出好描述的四个要素和四种失败模式
- [x] 能设计一个有效的消融实验：换问题而不是重复、放困难负样本、单变量控制
- [x] 能解释第一轮实验为什么没出差异
- [x] 能写出带轮数上限的多轮 Agent 循环，并说清两层循环的分工
- [x] 知道并行调用时 assistant 每轮 1 条、tool 每个调用 1 条
- [x] 能用字典分发和 `**` 解包调用工具
- [x] 知道为什么计算工具不能用 eval
- [x] 能区分 API 调用和本地执行，正确估算调用次数
- [x] 能把工具错误回填给模型，并区分工具层和系统层错误
- [x] 知道 `except Exception` 的风险和弥补办法
- [x] 能用生成机制解释「输出比输入贵」「TTFT 占比高」「缓存便宜」
- [x] 能区分 embedding 检索和关键词搜索
- [x] 能说清 temperature=0 为什么不能消除幻觉

---

## 附录 A：五步循环速查

```python
# 1. 带上 tools 发请求
payload = {..., "tools": tools}
message = call_llm(messages)

# 2. 判断有没有工具调用
if "tool_calls" not in message:
    return message["content"]

# 3. 原样追加模型的回复（每轮一次）
messages.append(message)

# 4. 逐个执行并回填（每个调用一次）
for tool_call in message["tool_calls"]:
    name = tool_call["function"]["name"]
    args = json.loads(tool_call["function"]["arguments"])
    result = tool_map[name](**args)
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": str(result),
    })

# 5. 再发一次，直到没有 tool_calls（循环 + 轮数上限）
```

## 附录 B：本周新语法

| 语法 | 例子 | 说明 |
|---|---|---|
| 元组解包 | `for q, e in test_cases:` | 直接拆成两个变量，不用下标 |
| `enumerate` | `for i, x in enumerate(lst, start=1):` | 同时拿到下标和元素 |
| 条件表达式 | `"✅" if a == b else "❌"` | 一行的 if/else |
| 百分比格式化 | `f"{0.7:.0%}"` → `70%` | 自动乘 100 加百分号 |
| 函数作为字典值 | `{"greet": greet}` | 不加括号，存函数本身 |
| `**` 解包 | `func(**{"a": 1})` | 字典拆成关键字参数 |
| `list.extend` | `tools.extend(more)` | 把列表元素逐个追加 |
| `str.join` | `"、".join(["北京", "上海"])` | 用分隔符连接列表元素 |
| `type(e).__name__` | 取异常的类型名 | 日志里快速识别错误类别 |

## 附录 C：提交记录

```
week5: function calling 5-step loop
week5: tool description ablation experiment (100% vs 70%)
week5: multi-round agent loop with parallel tool calls
week5: error handling and result backfill in agent loop
```

---

## 遗留任务

- **CostTracker 区分缓存命中价格**：本周实测误差约 40%，轮次越多误差越大
- **CostTracker 移到 `common/` 目录**：第 6 周第三次用到时搬家
- **工具参数预校验**：调用前比对声明，区分「模型传错」和「代码不一致」，错误信息里说明重试是否有用
- **tools 声明与 tool_map 统一来源**：注册函数时自动生成声明
- **第 4 周遗留**：多轮对话滑动窗口、few-shot 版简历抽取
- **消融实验扩大样本**：困难负样本扩充到二三十条，覆盖多种类型
- 可选：手算余弦相似度练习

---

## 下周预告

第 6 周：**RAG 基础链路**。

这周概念补课里讲的 embedding 和余弦相似度，下周会直接用上：把一批文档切分、向量化、存进向量库，用户提问时找出最相关的几段，塞进 prompt 让模型基于文档回答。

**RAG 和本周的 Function Calling 是同一个思路**：模型的知识是封闭的，要么让它调工具获取实时数据，要么给它塞真实文档。而当塞给它的文档**互相矛盾、或者有新有旧**时，模型会怎么选？这正是你的研究方向「记忆冲突与时间一致性」要回答的问题。
