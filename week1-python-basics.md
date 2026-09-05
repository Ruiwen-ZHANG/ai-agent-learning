# 从零学 AI Agent 开发：第 1 周技术总结（Python 工程基础）

> 这是我 16 周 AI Agent 学习计划的第一周记录。
> 起点：只会 Python 基础语法（变量、函数、循环、列表字典），类和异常都没碰过。
> 本周目标：补齐工程地基，为后面调用大模型 API 做准备。
>
> **这篇笔记最有价值的部分是第七章「典型错误合集」**——全是我自己撞出来的坑，
> 每个都附了错误代码、真实报错、根因分析和正确写法。

---

## 目录

- 一、本周学了什么
- 二、类与对象
- 三、类型注解
- 四、异常处理
- 五、三个标准库：pathlib / json / logging
- 六、环境管理与配置
- 七、⚠️ 典型错误合集（重点）
- 八、可复制模板库
- 九、本周形成的规则清单
- 十、独立编程实战

---

# 一、本周学了什么

五个模块，全部围绕"写出能上线的代码"而不是"能跑的代码"。

| 模块 | 核心内容 | 后面用在哪 |
|---|---|---|
| 类与对象 | 把数据和操作打包，实例独立 | 所有 Agent 框架都是类 |
| 类型注解 | 编写时发现错误 | Pydantic 校验工具参数 |
| 异常处理 | 出错时优雅降级 | 工具执行失败回填给模型 |
| pathlib | 跨平台路径处理 | RAG 遍历文档目录 |
| json | 结构化数据转换 | 解析模型返回的工具调用 |
| logging | 可追溯的运行记录 | Agent 链路追踪、成本监控 |
| 环境管理 | 依赖隔离、密钥保护 | 保护 API Key 不泄露 |

**学习方式**：每个知识点讲完立刻出题，然后从空白文件独立写一个完整的类。本周独立完成了两个：`ToolRegistry`（工具注册表）和 `TokenCounter`（token 计数器），都是后面真正会用到的组件。

---

# 二、类与对象

## 2.1 为什么需要类

用函数管理多轮对话，很快会遇到瓶颈：

```python
# 函数式写法的困境
messages = []

def add_message(messages, role, content):
    messages.append({"role": role, "content": content})

def count_tokens(messages):
    return sum(len(m["content"]) for m in messages)
```

问题在于：
- `messages` 要在每个函数间传来传去
- 想同时管理两个对话，得建 `messages_a`、`messages_b`，还得小心别传错
- 加个 `max_turns` 限制，每个函数都得多一个参数
- 别人读代码，不知道 `messages` 和 `max_turns` 是一伙的

**类解决的核心问题只有一个：把「数据」和「操作这些数据的函数」绑在一起，打包成一个可以复制多份的东西。**

```python
class Conversation:
    def __init__(self, system_prompt, max_turns=10):
        self.messages = [{"role": "system", "content": system_prompt}]
        self.max_turns = max_turns

    def add(self, role, content):
        self.messages.append({"role": role, "content": content})


conv_a = Conversation("你是一个helpful的助手")
conv_b = Conversation("你是一个严格的代码审查员", max_turns=5)
# 两个对话完全独立，互不干扰
```

## 2.2 self 到底是什么

这是最容易卡住的地方。**`self` 就是「发起这次调用的那个具体实例」。**

当你写：

```python
conv_a.add("user", "你好")
```

Python 实际执行的是：

```python
Conversation.add(conv_a, "user", "你好")
#                  ↑ conv_a 被自动塞到了第一个参数位
```

这解释了两件事：
- 为什么定义方法时写 3 个参数，调用时只传 2 个
- 为什么方法里访问数据必须写 `self.messages` 而不是 `messages`

**可以亲手验证**：

```python
class Demo:
    def who(self):
        print("self 指向:", self)
        print("它的 id:", id(self))


d1 = Demo()
d2 = Demo()
print("d1 的 id:", id(d1))
print("d2 的 id:", id(d2))
d1.who()   # 打印出的 id 和 d1 完全一致
d2.who()   # 这次和 d2 一致
```

实测输出：

```
d1 的 id: 2276266242608
d2 的 id: 2276266122832
self 指向: <__main__.Demo object at 0x00000211FC0A7230>
它的 id: 2276266242608          ← 和 d1 一致
self 指向: <__main__.Demo object at 0x00000211FC089E50>
它的 id: 2276266122832          ← 和 d2 一致
```

**还有一个等价写法能彻底说明问题：**

```python
conv.add("user", "你好")                    # 写法 A：语法糖
Conversation.add(conv, "user", "在吗")      # 写法 B：手动展开，效果完全一样
```

## 2.3 点号 vs 下划线（初学高频混淆）

```python
self.name = name      # ✅ 在 self 这个对象上，创建一个叫 name 的属性
self_name = name      # ❌ 创建了一个普通局部变量，和 self 毫无关系
```

**点号 `.` 表示「属于」**，是从属关系。下划线只是名字里的一个普通字符。

写错的后果：

```python
class ToolBox:
    def __init__(self, name):
        self_name = name         # 只是局部变量，方法执行完就销毁了

    def show(self):
        print(self.name)         # AttributeError: 'ToolBox' object has no attribute 'name'
```

而且 `__init__` 那一行**不会报错**，错误要等到 `show()` 被调用时才爆发。

**验证方法**：

```python
class Demo:
    def __init__(self, value):
        self.saved = value        # 存到实例上
        not_saved = value         # 普通局部变量


d = Demo("测试")
print(vars(d))     # {'saved': '测试'}  ← 只有 saved，not_saved 根本没被存下来
```

`vars(对象)` 返回实例所有属性组成的字典，调试时很有用。

## 2.4 实例属性 vs 类属性（重要陷阱）

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
class Agent:
    tools = []                    # ← 错误在这里：类属性

    def __init__(self, name):
        self.name = name

    def add_tool(self, tool):
        self.tools.append(tool)


a1 = Agent("助手1")
a2 = Agent("助手2")
a1.add_tool("搜索")
print(a2.tools)                   # ['搜索']  ← a2 什么都没做，却被污染了
```

**原因**：`tools = []` 写在类体里，属于 `Agent` 这个类本身，所有实例共享同一个列表对象。`self.tools.append(...)` 找不到实例属性，向上找到类属性，在这个共享列表上做了修改。

```python
# ✅ 正确写法
class Agent:
    DEFAULT_MODEL = "deepseek-chat"    # 类属性只放【不会被修改的常量】
    MAX_RETRIES = 3

    def __init__(self, name):
        self.name = name
        self.tools = []                # 可变对象一律在 __init__ 里初始化
```

**为什么 `self.count += 1` 反而没问题？**

因为 `+=` 对不可变对象（int）本质是**赋值**，而赋值会在**实例上**新建一个属性，把类属性遮住。所以这个坑**只在可变对象（list / dict / set）上暴露**——它们是原地修改，没触发赋值。

**推论**：想改类属性，必须用 `类名.属性名`，不能用 `self.属性名`。

```python
class Agent:
    total_tokens = 0            # 全系统累计

    def __init__(self, name):
        self.tokens = 0         # 这个 Agent 自己的

    def call_llm(self, prompt):
        used = len(prompt)
        self.tokens += used            # 记到自己账上
        Agent.total_tokens += used     # 累加到全局账上（必须用类名）
```

## 2.5 可变默认参数（同一问题的另一副面孔）

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def add_tool(name, registry=[]):     # ← 错误在这里
    registry.append(name)
    return registry


print(add_tool("搜索"))    # ['搜索']
print(add_tool("计算"))    # ['搜索', '计算']  ← 上次的数据还在！
```

**核心机制：默认参数的值，在函数「定义」的那一刻就创建好了，而不是每次调用时创建。**

整个程序运行期间，那个列表只有**一份**。

**可以亲眼看见它：**

```python
class ToolBox:
    def __init__(self, name, tools=[]):
        self.name = name
        self.tools = tools

    def register(self, tool):
        self.tools.append(tool)


print("定义时的默认值:", ToolBox.__init__.__defaults__)
# ([],)

box1 = ToolBox("工具箱1")
print("box1.tools 的 id:", id(box1.tools))
print("默认值的 id:", id(ToolBox.__init__.__defaults__[0]))
# 两个 id 完全一样 —— box1.tools 就是那个默认列表本身

box1.register("搜索")
print("register 之后:", ToolBox.__init__.__defaults__)
# (['搜索'],)  ← 震撼：函数的默认值本身被改掉了！
```

**你以为在改一个实例的数据，实际上你在改函数定义。**

```python
# ✅ 正确写法
def __init__(self, name, tools=None):
    self.name = name
    if tools is None:
        tools = []          # 每次调用都创建全新的列表
    self.tools = tools
```

**为什么用 `is None` 而不是 `== None`**：`is` 比较"是不是同一个对象"，`==` 比较"内容是否相等"（会调用 `__eq__`）。None 是单例，用 `is` 语义最准、速度最快，且不受某些库重写 `__eq__` 的影响。**PEP 8 明确规定和 None 比较必须用 `is`。**

**为什么不用 `self.tools = tools or []`**：`or` 判断真假值，而空列表是假值。如果调用方**故意传了空列表**想让对象持有它，这行会把它丢掉换成新的，调用方后续操作会发现没反应。

## 2.6 这个 bug 有多隐蔽

三个条件必须**同时满足**才暴露：

| 条件 | 说明 |
|---|---|
| ① 默认值是可变对象 | list / dict / set。int、str、None、元组都没事 |
| ② 调用时省略了该参数 | 显式传参就安全 |
| ③ 对它做了原地修改 | `append`/`update`/`add`。只读或用 `+` 生成新对象都没事 |

所以它常常在**上线后**才暴露：本地测试都传参，用户不传参，然后数据开始串台。

## 2.7 抽象的取舍：一个通用方法 + 若干便捷包装

`add_user` 和 `add_assistant` 只有一个字符串不同，可以抽成参数：

```python
def add(self, role, content):
    self.messages.append({"role": role, "content": content})
```

但这带来新问题：**调用方可能传错字符串**（`"User"`、`"assistan"`），而且不报错，直到发给 API 才失败。

实际项目的做法是**两层结构**：

```python
class Conversation:
    def add(self, role, content):
        """通用方法，承载真正的逻辑"""
        self.messages.append({"role": role, "content": content})
        self._trim()

    def add_user(self, content):
        """便捷方法，转手调 add，把 role 写死"""
        self.add("user", content)

    def add_assistant(self, content):
        self.add("assistant", content)
```

好处：
- 逻辑只有一份，以后加日志、加校验只改 `add` 一处
- 日常用便捷方法，拼错就立刻报 `AttributeError`
- 需要灵活时还有 `add("tool", ...)` 这个出口

**这种「一个通用实现 + 若干便捷包装」的结构在真实代码库里到处都是**，比如 `requests.get()` / `requests.post()` 本质都在调 `requests.request(method, ...)`。

## 2.8 魔术方法

方法名前后各两个下划线的叫「魔术方法」或 dunder 方法，Python 会在特定时机自动调用它们。

| 方法 | 让你能写 |
|---|---|
| `__init__` | `Conversation("...")` |
| `__len__` | `len(conv)` |
| `__str__` | `print(conv)` 显示友好文本 |
| `__contains__` | `"add" in registry` |
| `__eq__` | `obj1 == obj2` |
| `__iter__` | `for x in obj` |

```python
def __len__(self) -> int:
    return len(self.messages)

def __str__(self) -> str:
    return f"Conversation(共 {len(self.messages)} 条消息, max_turns={self.max_turns})"
```

没定义 `__str__` 时，`print(conv)` 输出的是 `<__main__.Conversation object at 0x...>`，对调试毫无帮助。

**魔术方法的名字是规定死的**，写错一个字母就不会被调用。而 `self.tools`、`self.messages` 这类属性名则完全自由。

---

# 三、类型注解

## 3.1 最关键的一点：注解不影响运行

```python
def repeat(text: str, times: int) -> str:
    return text * times


print(repeat("ab", 3))    # ababab
print(repeat(5, 3))       # 15   ← 不报错！
```

**Python 解释器完全跳过类型注解。** `ensure_ascii` 那样的运行时参数会影响行为，注解不会。

`repeat(5, 3)` 能跑，是因为 `5 * 3` 本身合法。而下面这个报错，报的是 `+` 这个操作，不是注解：

```python
def greet(name: str) -> str:
    return "你好，" + name

greet(123)     # TypeError: can only concatenate str (not "int") to str
```

**判断会不会报错，要看函数体里的运算能不能接受实际类型，和注解无关。**

## 3.2 那注解有什么用

四个理由：

**① 编写时就发现错误。** PyCharm 会在你敲下 `repeat(5, 3)` 的那一刻标黄，把错误从"运行时才发现"提前到"敲键盘的瞬间"。

**② 让代码自解释。** 别人（包括三个月后的你）看一眼签名就知道该传什么。

**③ 某些库会真的读取注解并校验。** Pydantic 就是这么干的，而它是整个 AI 生态的基础设施（LangChain、FastAPI、OpenAI SDK 全都依赖它）：

```python
from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


m2 = Message(role="user", content=123)
print(m2.content)            # '123'  ← 自动转成了字符串
m3 = Message(role="user")    # ❌ 直接报错：缺少必填字段 content
```

在这里注解**不再是摆设**，而是校验规则的来源。第 5 周做 Function Calling 时，模型返回的工具参数不可控，用 Pydantic 定义参数结构就能在执行工具**之前**拦住非法输入。

**④ 让 IDE 能自动补全和安全重构。** 没有注解，PyCharm 不知道变量是什么，补全列表是空的，改名重构只能做文本搜索。

## 3.3 一个更能说明问题的例子

```python
def get_names(users: list[str]) -> str:
    return ", ".join(users)


print(get_names(["张三", "李四"]))     # 张三, 李四
print(get_names("abc"))               # a, b, c   ← 没报错，但结果完全不对
```

**为什么会这样**：`join` 不要求参数是列表，只要求**可迭代**。而字符串是可迭代的——遍历它会逐个吐出**字符**。

```python
for ch in "abc":
    print(ch)      # a / b / c
```

于是 `", ".join("abc")` 得到 `a, b, c`。**语法正确，逻辑荒谬。**

这类 bug 最难查：程序不崩，输出看着"像那么回事"，但数据是错的。有注解的话，IDE 在你敲下 `get_names("abc")` 时就会标黄。

## 3.4 基础语法

```python
def add(a: int, b: int) -> int:      # 参数用冒号，返回值用箭头
    return a + b


def f(max_turns: int = 10):          # 带注解时等号两边【留】空格
    pass


def f2(max_turns=10):                # 无注解时等号两边【不留】空格
    pass


def add_user(self, content: str) -> None:    # 不返回值时标 None
    self.messages.append(...)
```

变量注解：

```python
count: int = 0
messages: list[dict[str, str]] = []
self.tools: dict[str, dict] = {}
```

## 3.5 容器类型要标清楚装的是什么

```python
names: list[str]                    # ["张三", "李四"]
scores: dict[str, int]              # {"数学": 90}  键 str，值 int
point: tuple[int, int]              # (10, 20) 定长，逐个标注
tags: set[str]
matrix: list[list[int]]             # 可以嵌套
versions: tuple[str, ...]           # 变长元组，... 表示"任意多个"
```

| 容器 | 需要几个类型 | 原因 |
|---|---|---|
| `list[str]` | 1 个 | 只有元素 |
| `set[str]` | 1 个 | 只有元素 |
| `dict[str, int]` | **2 个** | 键 + 值 |
| `tuple[int, int]` | 逐个写 | 定长，每个位置类型可不同 |
| `tuple[str, ...]` | 1 个 + 省略号 | 变长，元素类型一致 |

> `list[str]` 这种小写写法需要 Python 3.9+。老代码里的 `from typing import List` 然后 `List[str]` 是旧写法。

## 3.6 四个高频特殊类型

**`| None`——可能为空**

```python
def __init__(self, name: str, tools: list[str] | None = None):
    #                                 ↑ 竖线表示"或者"
```

**这里最容易混的一点**：等号两边的 `None` 是完全不同的东西。

```python
tools: list[str] | None = None
      └────────┬────────┘  └┬─┘
          类型注解        默认值
```

- 等号**左边**的 None 是**类型**的一部分：允许的类型里包含 NoneType
- 等号**右边**的 None 是**默认值**：调用时不传就用 None

一个描述"可以是什么"，一个规定"实际是什么"。

**规则：只要默认值是 `None`，类型注解里就必须有 `| None`**，否则自相矛盾。

**`Literal`——限定具体取值**

```python
from typing import Literal

Role = Literal["system", "user", "assistant", "tool"]     # 类型别名


def add(self, role: Role, content: str) -> None:
    ...
```

现在写 `conv.add("User", "你好")`，PyCharm 会立刻画波浪线：

```
Expected type 'Literal["system", "user", "assistant", "tool"]', got 'str' instead
```

**注意：Literal 违规永远不会在运行时报错。** 程序会正常把 `{"role": "User", ...}` 存进去，退出码 0。它的价值全部体现在编辑器里。

**`Any`——什么都行**

```python
from typing import Any


def parse_response(raw: str) -> dict[str, Any]:
    # 键一定是字符串，但值可能是字符串、数字、列表、嵌套字典
    return json.loads(raw)
```

能不用就不用，写 `Any` 和不写注解信息量差不多。真正需要它的场景是处理 JSON 这类结构不定的数据。

**`Callable`——参数是个函数**

```python
from typing import Callable


def get(self, name: str) -> Callable | None:
    ...
```

`Callable[[参数类型列表], 返回类型]`，参数部分要用方括号包起来。做 Agent 时会大量用到，因为工具本身就是函数。

## 3.7 注解写多少算合适

**一定要写**：所有函数/方法的参数和返回值、类的实例属性。

**不用写**：函数内部的临时变量——右边一看就知道类型。

```python
def _trim(self) -> None:
    limit = self.max_turns * 2        # 不用写 limit: int，一眼就知道
    kept = self.messages[-limit:]     # 切片结果显然是列表
```

**注解是为了消除歧义，不是为了显得严谨。**

## 3.8 三种常见的注解错误

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def get_config(path: str = None) -> dict:        # ← 类型少了 | None
    ...

def process(items: list) -> None:
    return len(items)                            # ← 标 None 却返回了值

def find_user(uid: int) -> dict[str]:            # ← dict 必须写两个类型
    ...
```

```python
# ✅ 正确写法
def get_config(path: str | None = None) -> dict:
    ...

def process(items: list) -> int:
    return len(items)

def find_user(uid: int) -> dict[str, Any] | None:
    ...
```

**核心教训：注解必须和代码的实际行为一致。写错的注解比不写更糟糕**——不写只是缺信息，写错是主动误导。

---

# 四、异常处理

## 4.1 为什么 Agent 离不开它

Agent 调用天气工具时，可能出的事：网络断了、API 限流、模型传的参数是"北京市"而不是"北京"、返回的 JSON 格式变了……

**没有异常处理，任何一个都会让整个 Agent 挂掉。** 而正确的行为应该是：捕获错误 → 把错误信息回填给模型 → 让模型自己纠正重试。

这个"错误回填重试"机制是 Agent 工程最核心的能力之一。

## 4.2 try / except 的执行流程

```python
try:
    print("第一行")
    x = 1 / 0
    print("第三行")      # ❌ 不会执行
except ZeroDivisionError:
    print("捕获了")
```

**异常一抛出，try 块内剩余代码直接放弃**，不是"跳过出错那一行继续"。

## 4.3 finally 连 return 都拦得住

```python
def f():
    try:
        print("A")
        x = 1 / 0
        print("B")
    except ZeroDivisionError:
        print("C")
        return "D"
    finally:
        print("E")
    print("F")

print(f())
```

输出是：

```
A
C
E
D
```

两个反直觉的点：

- **E 在 D 之前**。`return "D"` 只是准备好返回值，函数还没真正退出。`finally` 会插在 return 和真正退出之间。
- **F 不执行**。`except` 里执行了 return，函数已经决定退出，`finally` 跑完直接返回。

`finally` 会执行的场景：

| 场景 | 执行吗 |
|---|---|
| try 正常跑完 | ✅ |
| 异常被 except 捕获 | ✅ |
| 异常没人捕获（程序要崩了） | ✅ |
| try 或 except 里有 return | ✅（返回前执行） |

只有进程被强制杀死才不执行。

> 在 `finally` 里写 `return` 会吞掉原本的返回值甚至正在抛出的异常。知道有这回事，但永远别这么写。

## 4.4 绝对不要裸捕获

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def load_config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:                      # ← 灾难性写法
        return {}
```

这个 `except:` 会吞掉的东西：

| 真实发生的事 | 异常类型 | 调用方看到的 |
|---|---|---|
| 文件不存在 | FileNotFoundError | `{}` |
| 没有读取权限 | PermissionError | `{}` |
| 内容不是合法 JSON | JSONDecodeError | `{}` |
| **你忘了 import json** | NameError | `{}` |
| **把 json 拼成了 jsno** | NameError | `{}` |
| **用户按了 Ctrl+C** | KeyboardInterrupt | `{}` |

**七种完全不同的情况，全变成同一个 `{}`。** 最要命的是第 4、5 条——你自己的代码写错了，也被当成"配置读取失败"处理掉了。

而且调用方无法区分：这个空字典到底是"合法的空配置"还是"出错了"？两种截然不同的情况用同一个值表示，调用方无法做正确决策。

```python
# ✅ 正确写法
def load_config(path: str) -> dict:
    config_file = Path(path)

    if not config_file.exists():
        # 文件不存在是【预期内】的，用默认值合理，但要说出来
        print(f"[提示] 配置文件不存在，使用默认配置: {path}")
        return {}

    try:
        text = config_file.read_text(encoding="utf-8")
        return json.loads(text)
    except json.JSONDecodeError as e:
        # 文件存在但内容坏了 —— 这是真正的错误，不能静默降级
        raise ValueError(f"配置文件格式错误: {path}") from e

    # 注意：这里【没有】兜底的 except Exception
    # PermissionError、NameError 等继续往上抛，该崩就崩
```

**核心原则：只捕获你知道该怎么处理的异常。**

如果捕获后除了 `pass` 或返回默认值之外做不了任何有意义的事，就不要捕获——让它抛出去，交给上层，或者直接崩掉。

**崩溃是有价值的**：它把问题暴露在最接近根因的地方。静默降级则把问题推迟到很远的将来，那时你已经不知道从哪查起。

**唯一的例外是 Agent 执行外部工具**：

```python
try:
    result = tool_func(*args)
except Exception as e:        # 注意是 Exception，不是裸 except
    return f"工具执行失败: {type(e).__name__}: {e}"    # 错误信息被完整保留
```

区别在于：用的是 `except Exception`（裸 `except:` 连 KeyboardInterrupt 都吞），而且**错误信息被保留并返回了**，不是变成 `{}` 消失。

## 4.5 raise 还是返回特殊值

判断标准：**函数有没有完成它承诺的职责？**

| 场景 | 怎么做 | 理由 |
|---|---|---|
| 查询用户，用户不存在 | 返回 None | 查询完成了，"没有"就是答案 |
| 传入的年龄是 -5 | raise ValueError | 调用方传了不可能的值，是调用方的 bug |
| 空列表求平均值 | raise | 数学上无定义；返回 0 会让人以为"平均分是 0" |
| 网络请求超时 | **raise** | 职责未完成，且调用方需要区分超时/404/401 来决定是否重试 |

第四条容易判断错。超时**很常见**，但"常见"不等于"正常"——你什么都没拿到，而且不知道服务器是没收到、还是处理中、还是回包丢了。

如果超时返回 None，调用方无法区分"服务器返回空数据"和"网络超时"，而这两种情况的处理方式完全不同。

**同一个"找不到"，处理方式也可以不同**：

```python
def get(self, name):
    if name in self.tools:
        return self.tools[name]["func"]
    return None                 # "没找到"是正常结果


def call(self, name, *args):
    if name not in self.tools:
        raise ToolNotFoundError(...)    # 调用方明确要执行它，执行不了就是错误
```

## 4.6 自定义异常与继承分层

```python
class ToolError(Exception):
    """工具相关错误的基类"""


class ToolNotFoundError(ToolError):
    """工具不存在"""


class ToolExecutionError(ToolError):
    """工具执行失败"""
```

好处是调用方可以精确捕获：

```python
try:
    result = registry.call("get_weather", "北京")
except ToolNotFoundError:
    # 工具不存在 → 告诉模型换一个工具
    ...
except ToolExecutionError:
    # 工具存在但执行失败 → 让模型重试或换参数
    ...
```

**捕获父类能同时接住所有子类**，所以不需要区分时可以简写：

```python
except ToolError as e:
    return f"执行失败: {e}"
```

**注意异常类要定义在类外面、文件顶层**，不要嵌套进业务类里，否则外部得写 `ToolRegistry.ToolNotFoundError` 才能访问。

## 4.7 异常链：raise ... from e

```python
try:
    result = func(*args)
except Exception as e:
    raise ToolExecutionError(f"工具 {name} 执行失败") from e
    #                                                 ↑ 保留原始异常
```

报错会同时显示两层：

```
ZeroDivisionError: division by zero

The above exception was the direct cause of the following exception:

ToolExecutionError: 工具 divide 执行失败
```

既有业务语义，又保留技术细节。调用方可以用 `e.__cause__` 拿到原始异常。

**但要注意**：`from e` 保住的异常链只有 Python 代码能读，**模型读不到**。给模型的文本里必须显式包含根因：

```python
raise ToolExecutionError(
    f"工具 {name} 执行失败: {type(e).__name__}: {e}"
) from e
```

模型看到 `ZeroDivisionError: division by zero` 才知道是除零，能自己改参数重试。

## 4.8 分层设计：call 与 safe_call

这两个方法服务于不同的调用方：

| 方法 | 给谁用 | 行为 |
|---|---|---|
| `call` | 你自己的 Python 代码 | 出错就抛异常，让你立刻发现 bug |
| `safe_call` | Agent 循环 | 出错转成文本，让模型看到并纠正 |

```python
def safe_call(self, name: str, *args) -> str:
    try:
        result = self.call(name, *args)      # 复用 call，不重写取值逻辑
        return str(result)
    except ToolNotFoundError as e:
        return f"工具不存在: {e}"             # return，不是 raise
    except ToolExecutionError as e:
        return f"执行出错: {e}"
```

**为什么 Agent 需要 safe_call**：

```
用 safe_call（不抛异常）:
  第1轮: 模型说"调用 divide(10, 0)"
  第2轮: result = "执行出错: division by zero" → 回填给模型
         → 模型看到错误，说"我传错了，改成 divide(10, 2)"
  第3轮: result = "5.0" → 任务完成 ✅

用 call（抛异常）:
  第2轮: 抛出 ToolExecutionError → while 循环当场炸掉
         → 整个 Agent 挂了，模型永远不知道自己错了 ❌
```

**区别不在"能不能看到错误"，在于"程序能不能继续"。**

**异常的价值不在于报告错误（print 也能报告），而在于控制程序流向。**

---

# 五、三个标准库

## 5.1 pathlib

### 为什么不用字符串拼路径

**坑 1：反斜杠有特殊含义**

```python
path = "D:\new\test.txt"
print(path)
```

输出：

```
D:
ew	est.txt
```

因为 `\n` 是换行、`\t` 是制表符。

**坑 2：不同系统分隔符不同**（Windows 用 `\`，Mac/Linux 用 `/`），本地跑通、服务器全挂。

**坑 3：拼接容易多出斜杠**（`"D:/projects/" + "/" + name` → `D:/projects//name`）。

### pathlib 的解法

```python
from pathlib import Path

p = Path("D:/PythonProjects") / "config.json"
```

用 `/` 拼接。它会自动适配系统、处理多余斜杠、不受转义影响。左边必须是 Path 对象。

### 读取路径的各部分

```python
p = Path("D:/projects/agent/week2/notes.md")

p.name          # notes.md      完整文件名
p.stem          # notes         不带后缀
p.suffix        # .md           后缀【带点】
p.parent        # .../week2     所在目录
p.parent.name   # week2         父目录的名字
```

**注意 `.suffix` 带点**，判断时要写 `if p.suffix == ".json"`。

`.parent` 返回的还是 Path，所以能连用 `.parent.parent` 往上走两层。

### 最重要的技巧：`__file__`

相对路径 `Path("data")` 的含义是"**运行时的当前目录**下的 data"，而不是"代码文件旁边的 data"。

用一个比喻：你写纸条说"送到隔壁那栋楼"——你在家写的和快递员在公司读的，指向完全不同的地方。**相对路径就是"隔壁"，取决于读者站在哪。**

| 你在哪运行 | `Path("data")` 实际指向 |
|---|---|
| 在 `week1/` 下运行 | `week1/data` |
| 在项目根目录运行 | `根目录/data` ❌ |
| 在 `C:\` 下运行 | `C:\data` ❌ |

解决办法是用 `__file__`——Python 自动提供的变量，永远指向**这个 .py 文件自己**的位置：

```python
BASE_DIR = Path(__file__).resolve().parent
```

拆开三步：

```python
__file__                              # 当前脚本路径（可能是相对的）
Path(__file__).resolve()              # 转成绝对路径
Path(__file__).resolve().parent       # 取所在目录
```

**这一行几乎每个 Python 项目里都有。** 之后所有路径从它出发拼接，不管从哪运行都正确。

换个比喻：`Path("data")` 是"往前走 100 米"，`BASE_DIR / "data"` 是"北纬 39.9，东经 116.4"。

### 其他常用操作

```python
p.exists()       # 存在吗（文件或目录都算）
p.is_file()      # 是文件吗
p.is_dir()       # 是目录吗

folder.mkdir(parents=True, exist_ok=True)
# parents=True   缺失的上级目录一并创建
# exist_ok=True  已存在时不报错
# 这两个参数基本上永远都要带

p.write_text("内容", encoding="utf-8")
content = p.read_text(encoding="utf-8")
# encoding="utf-8" 必须写，否则 Windows 用 GBK，中文会乱码

for item in folder.iterdir():        # 列出直接子项
for f in folder.glob("*.py"):        # 当前层匹配
for f in folder.rglob("*.py"):       # 递归所有子目录
```

`glob` 和 `rglob` 的唯一区别是**要不要钻进子目录**。第 6 周做 RAG 时会用 `rglob("*.md")` 把整个文档目录的 markdown 全找出来。

### 逐行读文件

```python
with p.open("r", encoding="utf-8") as f:
    for line in f:
        print(line.strip())
```

**`for line in f` 拿到的每一行都带换行符**，不 strip 的话打印会多出空行（line 自带 `\n` + print 又加一个）。

```python
"  abc  ".strip()      # "abc"    去两头
"  abc  ".lstrip()     # "abc  "  只去左边
"  abc  ".rstrip()     # "  abc"  只去右边（读文件时更精确，保留缩进）
```

**调试技巧**：用 `repr()` 让隐藏字符现形。

```python
print(repr(line))      # '第一行\n'  ← 换行符原样显示出来
```

`with` 语句保证文件用完自动关闭，**即使中间抛异常也会关**——它内部就是靠 `finally` 实现的。

## 5.2 json

### JSON 与 Python 的五个差异

| | Python | JSON |
|---|---|---|
| 引号 | 单双都行 | **只能双引号** |
| 尾随逗号 | 允许 | **不允许** |
| 布尔值 | `True` / `False` | **`true` / `false`** |
| 空值 | `None` | **`null`** |
| 注释 | `#` | **不支持** |

**这五条是模型生成 JSON 时最常犯的错误来源。**

判断合法性练习：

```
{"name": "张三"}                 ✅
{'name': '张三'}                 ❌ 单引号
{"name": "张三", "age": 28,}     ❌ 尾随逗号
[1, 2, 3]                        ✅ 顶层可以是数组
{"active": True}                 ❌ 必须小写 true
{"score": null}                  ✅
```

**顶层不一定是对象**，数组、字符串、数字、布尔、null 都可以：

```python
json.loads("[1, 2, 3]")     # [1, 2, 3]
json.loads('"hello"')       # hello
json.loads("42")            # 42
json.loads("true")          # True
json.loads("null")          # None
```

`to_schema()` 返回的列表转成 JSON 后，顶层就是数组。

### 四个函数

| 函数 | 方向 | 操作对象 |
|---|---|---|
| `json.dumps()` | Python → 文本 | **字符串** |
| `json.loads()` | 文本 → Python | **字符串** |
| `json.dump()` | Python → 文件 | 文件对象 |
| `json.load()` | 文件 → Python | 文件对象 |

记忆法：`dump` = 倒出去，`load` = 装进来；**带 s 的处理 string**。

**推荐统一用带 s 的版本配合 pathlib**：

- 数据来源不一定是文件（模型返回、网络请求都是字符串）
- 和 pathlib 风格一致，一行搞定
- 字符串在手，随时能打印检查

### 中文必须加的参数

```python
data = {"城市": "北京", "温度": 25}

json.dumps(data)
# {"\u57ce\u5e02": "\u5317\u4eac", "\u6e29\u5ea6": 25}   ← 合法但没法读

json.dumps(data, ensure_ascii=False, indent=2)
# {
#   "城市": "北京",
#   "温度": 25
# }
```

**`ensure_ascii=True`（默认）不是"禁止中文"，而是"把中文转成 ASCII 转义序列"。** 它依然是合法 JSON，解析回来还是中文，只是可读性极差。

**注意输出的是双引号**——`dumps` 产出的是 JSON 文本。而 `print(字典)` 显示的是 Python 对象形式，用单引号。**看引号就能判断你手上的是什么。**

### 完整读写模板

```python
# 写
config_file.write_text(
    json.dumps(data, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

# 读
data = json.loads(config_file.read_text(encoding="utf-8"))
```

**两个编码参数都要带**，漏了任何一个中文都会出问题。

### 处理模型返回的 Markdown 包裹

模型返回 JSON 时经常带代码块：

````
```json
{"tool": "get_weather", "city": "北京"}
```
````

直接 `json.loads` 会失败，需要先清理：

```python
def parse_model_json(text: str) -> dict:
    """解析模型返回的 JSON，容忍 Markdown 代码块包裹。"""
    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:-1]              # 去掉首尾两行
        text = "\n".join(lines)

    return json.loads(text)
```

第 5 周会大量用到这个函数。

## 5.3 logging

### 为什么放弃 print

| 问题 | 说明 |
|---|---|
| 没有级别 | "开始处理"和"数据库连不上"输出长得一样 |
| 关不掉 | 上线要手动注释掉每一条 |
| 没有时间和位置 | 不知道什么时候、哪一行打的 |
| 只能输出到屏幕 | 服务器上关了窗口日志就没了 |

### 五个级别

| 级别 | 什么时候用 |
|---|---|
| DEBUG | 详细调试信息，只在排查时看 |
| INFO | 正常流程的关键节点 |
| WARNING | 有问题但能继续 |
| ERROR | 出错了，某个功能失败 |
| CRITICAL | 严重错误，程序可能要挂 |

设置 `level` 就是设置门槛，低于它的全部丢弃。**这就解决了"关不掉"的问题**——开发设 DEBUG，上线改 INFO，一行配置搞定，不用动任何日志语句。

### exception 不是第六个级别

```python
logger.exception("计算失败")
# 完全等价于
logger.error("计算失败", exc_info=True)
```

**级别是 ERROR**，`exception()` 只是帮你省掉 `exc_info=True` 这个参数，作用是把完整 Traceback 附在日志后面。

对比效果：

```
[ERROR] 用 error: division by zero          ← 只知道除零了

[ERROR] 用 exception
Traceback (most recent call last):
  File "demo.py", line 13, in <module>
    1 / 0
ZeroDivisionError: division by zero          ← 精确到文件和行号
```

**只能在 except 块里用。** 在外面调用会打印 `NoneType: None`，因为它靠"当前正在处理的异常"来抓取信息。

| 场景 | 用什么 |
|---|---|
| except 块里，意料之外的错误 | `logger.exception(...)` |
| except 块里，预期内且有预案 | `logger.warning(f"...: {e}")` |
| 不在 except 块里 | `logger.error(...)` |

### getLogger(\_\_name\_\_) 的价值

```python
logger = logging.getLogger(__name__)
```

对比根 logger：

```
用根 logger：
2026-09-02 14:30:15 [INFO] root - 工具已注册
2026-09-02 14:30:16 [INFO] root - 消息已添加      ← 全是 root，不知道谁打的

用 getLogger(__name__)：
2026-09-02 14:30:15 [INFO] tool_registry - 工具已注册
2026-09-02 14:30:16 [INFO] conversation - 消息已添加    ← 一眼看出来源
```

更实用的好处是**可以分模块控制级别**：

```python
logging.basicConfig(level=logging.INFO)
logging.getLogger("tool_registry").setLevel(logging.DEBUG)   # 单独调详细
logging.getLogger("httpx").setLevel(logging.WARNING)         # 让吵闹的库闭嘴
```

`__name__` 是当前模块名。**直接运行的脚本，`__name__` 固定是 `__main__`**——这也解释了 `<__main__.Demo object at 0x...>` 里的 `__main__` 是什么。

### handlers：日志的输出目的地

```
logger.info("消息")
      ↓ 级别检查
   交给所有 handler
   ┌─────┴─────┐
   ↓           ↓
FileHandler  StreamHandler
（写文件）    （打屏幕）
```

**一条日志会被发给列表里的每一个 handler。**

```python
handlers=[
    logging.FileHandler(log_file, encoding="utf-8", mode="w"),
    logging.StreamHandler(sys.stdout),
]
```

- `mode="w"` 每次运行清空（学习用）；`mode="a"`（默认）追加（生产必须用）
- `StreamHandler()` 默认输出到 **stderr**，在 PyCharm 里显示为红色。传 `sys.stdout` 可以变成正常白色，而且 print 和日志的**输出顺序会变正常**（stdout 和 stderr 是两个独立缓冲区，各自刷新，交错顺序不可预测）

### ⚠️ basicConfig 必须在第一条日志之前

**这是本节最重要的坑**，因为它**静默失效，不报任何错**。

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
logger = logging.getLogger(__name__)
logger.info("程序启动")          # ← 第一条日志在这里就打出去了

logging.basicConfig(             # ← 太晚了，完全不生效
    level=logging.INFO,
    handlers=[logging.FileHandler("app.log", encoding="utf-8")],
)

logger.info("处理数据")
```

后果：级别配置没生效、格式没生效、**日志文件是空的甚至没被创建**。而 Python 一句警告都不给。

原因：一旦有日志被打出去，logging 会自动给根 logger 装一个默认 handler，之后再调 `basicConfig` 就无效了。

**正确位置：紧跟 import。**

```python
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(...)          # ← 这里

logger = logging.getLogger(__name__)

# 下面才是类定义和业务代码
```

（路径三行必须在 basicConfig 前面，因为 FileHandler 要用到 `DATA_DIR`。）

### 三个库的共同坑：编码

- pathlib：`encoding="utf-8"`
- json：`ensure_ascii=False`
- logging：`FileHandler(..., encoding="utf-8")`

**三处都要单独设置，漏一个中文就出问题。**

---

# 六、环境管理与配置

## 6.1 虚拟环境

每个项目拥有自己独立的一套库，互不干扰。PyCharm 建项目时自动创建的 `.venv` 文件夹就是。

终端提示符前的 `(.venv)` 表示环境已激活——**装的库会进这个项目，不会污染全局 Python**。看不到这个前缀时要手动激活：`.venv\Scripts\activate`。

## 6.2 uv

Rust 写的包管理工具，比 pip 快 10-100 倍，现已成为社区主流。

```bash
pip install uv

uv pip install requests            # 注意是 uv pip install，不是 uv install
uv pip list
uv pip freeze > requirements.txt
uv pip install -r requirements.txt
```

**国内网络问题**：直连 PyPI 经常失败，报 `Could not find a version that satisfies the requirement`（注意 `from versions: none` 说明是网络问题，不是包不存在）。一次性配好镜像：

```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

之后所有 `pip install` 自动走清华源。

## 6.3 requirements.txt

记录项目依赖哪些库、什么版本。

```
python-dotenv==1.2.3
httpx==0.27.2
```

`==` 是精确版本。不锁版本的话，半年后别人装到的是最新版，API 可能已经改了——**这就是经典的"我这能跑，你那不行"**。

`freeze` 的缺点是会把环境里所有东西都记下来，包括 `uv`、`pip` 这类开发工具和你临时试装的库。**真实项目会手动整理，判断标准是：你的代码里 `import` 了它吗？**

## 6.4 .env 与密钥保护

```python
API_KEY = "sk-abc123def456..."      # ❌ 绝对不能这么写
```

三个严重问题：

1. **提交到 GitHub = 密钥泄露。** 有爬虫专门扫描 `sk-` 开头的字符串，几分钟内就被盗刷
2. 换环境要改代码
3. 团队协作时每个人 key 不同，一提交就冲突

正确做法是把配置放进 `.env`：

```
APP_NAME=我的Agent
MODEL_NAME=deepseek-chat
MAX_TURNS=10
DEBUG=false
API_KEY=sk-xxxxx
```

格式规则：一行一个，**等号两边不加空格**，**值不加引号**，`#` 开头是注释。

## 6.5 读取环境变量

```python
import os
from dotenv import load_dotenv

load_dotenv()                          # 必须在所有 getenv 之前
api_key = os.getenv("API_KEY")
model = os.getenv("MODEL_NAME", "deepseek-chat")     # 第二个参数是默认值
```

**又是"配置在前，使用在后"。** 这条规则本周出现了三次：

| 场景 | 必须先做 | 才能后做 |
|---|---|---|
| logging | `basicConfig()` | 打日志 |
| dotenv | `load_dotenv()` | `os.getenv()` |
| 路径 | 算出 `BASE_DIR` | 拼接子路径 |

## 6.6 load_dotenv 的查找机制

它不是"只找当前目录"，而是**从运行时的当前目录开始向上逐层查找**。所以有时候不指定路径也能找到——但这是**碰巧**。

```bash
cd C:\
python D:\project\week1\demo.py
# 当前目录是 C:\，一路往上找不到 .env
```

**而且找不到时不报错**，只是什么都不加载。之后所有 `getenv` 返回 None，你会以为是配置写错了，实际是文件根本没被读到。

**显式指定路径 + 存在性检查**：

```python
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR.parent / ".env"          # 脚本在 week1/，.env 在上一层

if not ENV_FILE.exists():
    raise FileNotFoundError(
        f"未找到配置文件: {ENV_FILE}\n请复制 .env.example 为 .env 并填入配置"
    )

load_dotenv(ENV_FILE)
```

这样"文件缺失"和"配置项缺失"就区分开了，报错信息直接指向真正的原因。

## 6.7 环境变量都是字符串

`.env` 是纯文本，里面的 `10` 是"字符1+字符0"，不是数字。**必须自己转换**：

```python
max_turns = int(os.getenv("MAX_TURNS", "10"))
#                                       ↑ 默认值也要写字符串
temperature = float(os.getenv("TEMPERATURE", "0.7"))
```

**布尔值是个坑：**

```python
debug = bool(os.getenv("DEBUG", "False"))     # ❌ 永远是 True！
```

因为 `bool("False")` 是 `True`——**任何非空字符串在 Python 里都是真值**，包括 `"False"`、`"0"`、`"no"`。配置里写 `DEBUG=False`，调试模式却一直开着。

```python
debug = os.getenv("DEBUG", "false").lower() == "true"     # ✅
```

## 6.8 必填项校验

```python
def check_required_config() -> None:
    """校验必填项，一次性列出所有缺失的键。"""
    required = ["API_KEY", "MODEL_NAME"]
    missing = [key for key in required if not os.getenv(key)]

    if missing:
        raise ValueError(f"缺少必需的配置项: {missing}\n请检查: {ENV_FILE}")
```

**一次性检查所有必填项**，而不是让用户改一个跑一次、发现又缺一个。

用 `not os.getenv(key)` 而不是 `is None`——空字符串（`API_KEY=` 但没填值）也要算缺失。

## 6.9 .gitignore

Git 默认跟踪所有文件，但有些不该被跟踪：

```
# 环境变量（含密钥，绝不提交）
.env

# 虚拟环境
.venv/

# Python 缓存
__pycache__/
*.pyc

# IDE 配置
.idea/
.vscode/

# 日志和数据
*.log
data/
```

### 两个必须记住的坑

**坑 1：只对"还没被追踪"的文件有效。**

```
情况 A（正确）：建 .gitignore → 写 .env → 提交    ✅ 安全
情况 B（危险）：写 .env → 提交 → 才建 .gitignore  ❌ 无效
```

情况 B 需要 `git rm --cached .env` 手动移除。**而且历史提交里那份还在**——如果已推到 GitHub，密钥就算泄露了，**唯一正确的补救是去平台重新生成密钥，把旧的作废**。

**所以规则是：项目建好的第一件事就是写 .gitignore。**

**坑 2：`.gitignore` 自己要被提交。**

| 文件 | 提交吗 | 原因 |
|---|---|---|
| `.gitignore` | ✅ | 团队共享的规则 |
| `.env.example` | ✅ | 模板，不含真实密钥 |
| `.env` | ❌ | 含真实密钥 |

---

# 七、⚠️ 典型错误合集

> **本章所有标注 ❌ 的代码都是错误示范，请勿复制。**
> 正确写法紧跟在每个错误之后，用 ✅ 标注。

这些全是我这周自己撞出来的。按**根因**分类，因为同一个认知盲区会以不同面貌反复出现——我最多的一个错误连续犯了三次。

## 7.1 【犯了 3 次】方法要调用，不能赋值

### 现场一

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def add_user(self, content):
    self.messages.append = [{"role": "user", "content": content}]    # ← 错误在这里
```

真实报错：

```
AttributeError: 'list' object attribute 'append' is read-only
```

### 现场二

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def get(self, name):
    if name in self.tools:
        self.tools.get = func      # ← 错误在这里
```

### 现场三

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def record(self, model, prompt_tokens, completion_tokens):
    self.record = {"model": model, ...}    # ← 属性名和方法名重名，把方法覆盖了
```

第三次的后果更隐蔽：第一次调用能跑，**第二次调用报 `TypeError: 'dict' object is not callable`**，因为 `self.record` 已经不是方法了。

### 根因

**小括号 `()` 表示「执行这个功能」，等号 `=` 表示「把左边换成右边」。**

| 你要做的事 | 写法 |
|---|---|
| 让方法产出一个值给调用方 | `return 值` |
| 让方法修改对象状态 | `self.属性 = 值`（属性名不能和方法名重名） |
| 执行某个方法 | `对象.方法(参数)` |

```python
# ✅ 正确写法
self.messages.append({"role": "user", "content": content})    # 调用，有括号，无等号
return self.tools[name]["func"]                                # 取值并返回
self.records.append({...})                                     # 属性名 records，方法名 record，不冲突
```

### 衍生错误：忘写 self

```python
# ❌❌❌ 错误示范 ❌❌❌
class Tool:
    def run():          # ← 忘了 self
        print("执行")

Tool().run()
```

报错：

```
TypeError: run() takes 0 positional arguments but 1 was given
```

第一次看很懵："我一个参数都没传，怎么说给了 1 个？" **那 1 个就是 Python 自动塞进去的实例。**

**以后见到 `takes 0 positional arguments but 1 was given`，第一反应就是：方法忘写 self 了。**

## 7.2 【犯了 2 次】混淆"容器"和"容器里的东西"

### 现场一：ToolRegistry

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
class ToolRegistry:
    def __init__(self, name, func, description):     # ← 错误在这里
        self.name = name
        self.func = func
        self.description = description
```

### 现场二：TokenCounter（同样的错误再犯一次）

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
class TokenCounter:
    def __init__(self, model, prompt_tokens, completion_tokens):    # ← 错误在这里
        self.model = model
```

### 根因

**`ToolRegistry` 是柜子，不是柜子里的一件工具；`TokenCounter` 是账本，不是一笔账。**

看验收测试就能发现：

```python
reg = ToolRegistry()        # 括号是空的！
c = TokenCounter()          # 括号也是空的！
```

新建一个柜子/账本时，里面**什么都没有**。`model`、`func` 这些是 `register()` / `record()` 的参数。

**`__init__` 的职责是「准备好空容器」，不是「装东西进去」。**

```python
# ✅ 正确写法
def __init__(self) -> None:
    self.tools: dict[str, dict] = {}      # 空柜子

def __init__(self) -> None:
    self.records: list[dict] = []          # 空账本
```

### 怎么避免再犯

**写任何类之前，先在文件顶部用注释画出数据结构。** 这一步不能跳。

```python
# self.tools 的结构：
# {
#     "工具名": {"func": 函数对象, "description": "描述文字"},
# }
```

数据结构定了，所有方法怎么写就都清楚了——方法无非是对这个结构做增删改查。

我两次卡住，都是因为跳过了这一步。

## 7.3 【犯了 3 次】记录 ≠ 中断

### 现场一

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def call(self, name, *args):
    if name not in self.tools:
        print("ValueError")           # ← 只打印了七个字母，程序继续往下跑
```

### 现场二

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def call(self, name, *args):
    if name not in self.tools:
        logger.exception(f"工具不存在: {name}")    # ← 只记了日志，没有 raise

    try:
        return self.tools[name]["func"](*args)     # ← 于是走到这里，KeyError
```

日志证据（这条链一目了然）：

```
[ERROR] 工具不存在: 不存在，已注册: ['add', 'divide']
NoneType: None                    ← exception 在 except 块外调用的症状
[INFO] 调用函数: 不存在            ← 已经知道不存在了，还是继续执行了！
[ERROR] 工具 不存在 执行失败: '不存在'
KeyError: '不存在'
```

### 现场三

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def total(self) -> int:
    total_count = 0
    for record in self.records:
        total_count += record["prompt_tokens"] + record["completion_tokens"]
    logger.info(f"总计消费tokens:{total_count}")
    # ← 缺 return，实际返回 None
```

### 根因

| 动作 | 作用 | 会中断执行吗 |
|---|---|---|
| `print(...)` | 打印到屏幕 | ❌ |
| `logger.error(...)` | 记录日志 | ❌ |
| `logger.exception(...)` | 记录日志 + Traceback | ❌ |
| `return 值` | 把值交给调用方并退出函数 | ✅（退出，不算"错误"） |
| `raise XxxError(...)` | 抛出异常 | ✅ |

**只有 `raise` 能改变程序流向。日志再详细，程序该往下跑还是往下跑。**

```python
# ✅ 正确写法
if name not in self.tools:
    raise ToolNotFoundError(f"工具不存在: {name}，已注册: {self.list_names()}")
    # raise 之后不需要 return，异常一抛方法立刻终止
```

## 7.4 【犯了 3 次】缩进与层级

### 现场一：异常类被写进了业务类内部

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
class ToolRegistry:
    class ToolError(Exception):          # ← 缩进了，成了嵌套类
        """工具相关错误的基类"""

    class ToolNotFoundError(ToolError):
        """工具不存在"""
```

后果：外部必须写 `ToolRegistry.ToolNotFoundError` 才能访问，`except ToolNotFoundError` 直接 NameError。

### 现场二：类定义写了两遍

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
class TokenCounter:
    class TokenCounter:              # ← 多余的一层
        def __init__(self):
            self.records = []
```

外部 `TokenCounter()` 创建出来的是空壳，里面什么方法都没有。

### 现场三：return 跑进了循环里

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def by_model(self):
    result = {}
    for record in self.records:
        model = record["model"]
        result[model] = result.get(model, 0) + tokens
        return result            # ← 和循环体对齐了，第一轮就返回
```

第一条记录处理完就返回，后面全部不处理。

### 现场四：__len__ 缩进错位

```python
# 缩进到了 class 那一级，变成模块级函数
```

报错：

```
TypeError: object of type 'Conversation' has no len()
```

### 排查工具

```python
print(hasattr(conv, "__len__"))     # False 说明没定义或缩进错了
```

### 根因

Python 用缩进表示层级，**缩进错了不一定报语法错误，但语义完全变了**。

**养成习惯**：写完一个类，从上往下扫一遍，确认所有 `def` 的缩进完全对齐。

## 7.5 【犯了 4 次】错误信息不带具体值

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
print("警告")
print("错误信息")
print("ValueError")
raise ToolNotFoundError()                        # 括号空的
raise ValueError(f"prompt_tokens不能为负数")      # 加了 f 但没用到变量
```

**这些信息等于没说。** 线上日志几千行，看到"警告"两个字，你完全不知道发生了什么。

```python
# ✅ 正确写法
print(f"[警告] 工具 {name} 已存在，将被覆盖")
raise ValueError(f"prompt_tokens 不能为负: {prompt_tokens}")
raise ToolNotFoundError(f"工具不存在: {name}，已注册: {self.list_names()}")
logger.exception(f"工具 {name} 执行失败, 参数={args}")
```

**规则：错误信息和日志必须包含触发它的具体值。**

好的错误信息还应该**告诉用户怎么解决**：

```python
raise FileNotFoundError(
    f"未找到配置文件: {ENV_FILE}\n"
    f"请复制 .env.example 为 .env 并填入你自己的配置"
)
```

## 7.6 【犯了 2 次】混淆"编写时"和"运行时"

### 现场一

我以为 `repeat(5, 3)` 会因为注解 `text: str` 而报错。**实际输出 15。**

### 现场二

我拿运行时的 `AttributeError` 当作 Literal 生效的证据。实际那个报错是"方法不存在"，**根本没走到检查参数的环节**。

### 根因

| 机制 | 生效时机 | 违规表现 |
|---|---|---|
| 类型注解 / Literal | 编写时（IDE） | 波浪线，**运行时静默通过** |
| `isinstance` 检查 | 运行时 | 抛异常 |
| Pydantic 校验 | 运行时（创建对象时） | 抛 ValidationError |
| mypy | 提交前（命令行） | 终端输出错误列表 |

**同样是"类型不对"，这四种机制的报错位置完全不同。**

Literal 生效的正确验证方式是**看编辑器里的波浪线**，不是看运行结果。

实测：写 `conv.add("User", "你好")` 和 `conv.add_user(123)`，PyCharm 都画了黄色波浪线；但程序照样跑完，退出码 0，两条非法数据老老实实进了 messages。

**判断一个机制有没有生效，要先想清楚：它是在什么时机工作的？**

## 7.7 数据类型用错方法

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def __len__(self) -> int:
    return len(self.records.keys())     # ← records 是列表，没有 .keys()

def by_model(self, model):
    for record in self.records[model]:  # ← 列表不能用名字索引
        ...
```

`.keys()` 是字典的方法。我在 `ToolRegistry.list_names()` 里用过——**那时 `self.tools` 是字典。这次数据结构变成列表了，方法也要跟着变。**

```python
# ✅ 正确写法
return len(self.records)          # 列表直接 len()
```

## 7.8 把类型注解当函数调用

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def register(self, name, func, description) -> list:
    ...
    return list[str](self.name)      # ← 把注解语法当成了创建列表的函数
```

**注解只能出现在两个位置：冒号后面、箭头后面。不能出现在表达式里。**

```python
# ✅ 正确写法
names = []                          # 空列表
names = list(self.tools.keys())     # 从字典的键构造列表
```

## 7.9 多加了不该有的参数

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def list_names(self, name):             # ← 不该有 name
    return list(self.tools[name])

def to_schema(self, name, description):  # ← 不该有这两个参数
    ...

def by_model(self, model):               # ← 不该有 model
    ...
```

**判断标准：这个信息 self 身上有吗？**

- 有 → 不用传参，直接 `self.xxx` 取
- 没有 → 才需要调用方传进来

`get(name)` 需要 `name`，因为"你要哪个工具"self 不知道。
`list_names()` 不需要参数，因为"所有工具名"self 全都有。

**这正是"把数据和操作打包成类"的意义：数据存在实例上，所有方法共享，不用来回传参。**

## 7.10 要捕获某异常，必须有代码抛出它

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def safe_call(self, name, *args) -> str:
    try:
        return self.tools[name]["func"](*args)     # ← 直接操作 tools，没调 call
    except ToolNotFoundError as e:                  # ← 永远进不来
        return str(e)
    except ToolExecutionError as e:
        return str(e)
```

`ToolNotFoundError` 是 `call` 方法抛的。`safe_call` 里没有调用 `call`，那句 `raise` 就没被执行，异常自然不会出现。

`name` 不存在时实际抛的是 `KeyError`，两个 except 都不匹配，异常穿透出去导致崩溃。

```python
# ✅ 正确写法
def safe_call(self, name: str, *args) -> str:
    try:
        result = self.call(name, *args)     # 调用会抛出那些异常的代码
        return str(result)
    except ToolNotFoundError as e:
        return f"工具不存在: {e}"
    except ToolExecutionError as e:
        return f"执行出错: {e}"
```

**写 `except XxxError` 之前，先问自己：try 块里哪一行会抛出这个异常？答不上来就是写错了。**

## 7.11 自定义异常遮蔽了库的异常

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
import json

class JSONDecodeError(Exception):       # ← 自己定义了一个同名的空类
    pass

try:
    data = json.loads(text)
except JSONDecodeError:                  # ← 捕获的是【你自己的】那个，永远匹配不上
    ...
```

`JSONDecodeError` 是 json 库自带的，`import json` 之后加前缀就能用。

```python
# ✅ 正确写法
except json.JSONDecodeError as e:
    print(f"JSON 格式错误 [{path.name}]: {e}")
    return {}
```

实测报错信息（**注意它精确到了行列**）：

```
JSON 格式错误 [bad.json]: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
```

**这就是为什么错误信息里一定要带 `{e}`**——它比你自己写的任何描述都有用。

## 7.12 Python 语法 vs 文本内容

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
data = {这不是json}                    # ← Python 会把它当变量名去找
bad_json.write_text(json.dumps(data))  # ← dumps 产出的永远是【合法】JSON
```

报错：

```
NameError: name '这不是json' is not defined
```

要造一个**坏的 JSON 文件**，必须绕过 json 库，把那段文字当**纯文本**写进去：

```python
# ✅ 正确写法
bad_json.write_text("{这不是json}", encoding="utf-8")
#                   ↑ 加引号，这是一段普通文本
```

## 7.13 变量名不能包含点号

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
agent.log = DATA_DIR / "agent.log"
```

Python 把 `agent.log` 理解成"agent 对象的 log 属性"，而 `agent` 不存在 → `NameError`。

```python
# ✅ 正确写法
log_file = DATA_DIR / "agent.log"
#  ↑ 变量名                ↑ 文件名（在引号里，随便写）
```

变量名合法字符只有：字母、数字、下划线，且不能以数字开头。

## 7.14 路径没拼接，文件掉在外面

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
folder = BASE_DIR / "data"
folder.mkdir(parents=True, exist_ok=True)

a = Path("a.txt")                      # ← 相对路径，指向"运行时的当前目录"
a.write_text("内容", encoding="utf-8")
```

结果：`data` 目录建好了但是空的，三个文件掉在了外面。

```python
# ✅ 正确写法
a = folder / "a.txt"                   # 拼到 folder 下面
```

同类错误还有把目录当文件用：

```python
# ❌❌❌ 错误示范 ❌❌❌
DATA_DIR = BASE_DIR / "config.json"          # 这是文件名，却当目录用
DATA_DIR.mkdir(parents=True, exist_ok=True)  # 建了一个【名叫 config.json 的文件夹】
```

以及命名和实际含义不符：

```python
# ❌ 名字给错了对象
data_dir = Path(__file__).resolve().parent   # 这其实是脚本目录
folder = data_dir / "data"                   # 这才是 data 目录

# ✅ 名副其实
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
```

## 7.15 把提示里的占位符当代码抄

```python
# ❌❌❌ 错误示范 ❌❌❌
for k, v in self.tools.items():
    result.append(...)          # ← 把教程里表示"这里你自己填"的 ... 抄进去了
```

输出：

```
schema: [Ellipsis, Ellipsis]
```

`...` 在 Python 里是一个合法对象（`Ellipsis`，主要用于 `tuple[str, ...]` 这类注解），所以不报错，就这么原样存进列表了。

## 7.16 max(字典) 默认比的是键

```python
# ❌❌❌ 错误示范 ❌❌❌
return max(stats)         # 按【键】的字母序比较

# ✅ 正确写法
return max(stats, key=stats.get)      # 按【值】比较
```

```python
d = {"apple": 100, "banana": 5}
max(d)                # 'banana'   ← 字母序 b > a
max(d, key=d.get)     # 'apple'    ← 值 100 > 5
```

**注意 `stats.get` 后面没有括号**——传的是函数本身，`max` 会自己去调。这和把函数存进字典是同一个概念：**函数可以当值传来传去。**

别忘了空字典要特殊处理：

```python
def top_model(self) -> str | None:
    stats = self.by_model()
    if not stats:              # 空字典是假值
        return None
    return max(stats, key=stats.get)
```

## 7.17 定义了方法却没人调用

```python
# ❌ Python 不会有任何提示
def add_user(self, content):
    self.messages.append({"role": "user", "content": content})
    # ← 少了 self._trim()
```

现象：`max_turns=2` 却存了 11 条消息，`_trim` 一次都没执行。

**程序照常跑完，退出码 0，一切看起来正常。**

这就是为什么写代码要有**预期输出**的习惯——事先知道"应该是 5 条"，一看是 11 条立刻察觉。

**推论：任何有裁剪、过滤、去重逻辑的代码，都要构造一个必然触发该逻辑的测试用例。只测正常路径的代码，等于没测。**

排查方法：

```python
def _trim(self) -> None:
    print(">>> _trim 被调用了，当前", len(self.messages), "条")    # 临时调试
```

三种结果对应三种病因：

| 现象 | 病因 |
|---|---|
| 完全看不到打印 | 没被调用 |
| 打印了但从没触发裁剪 | if 条件从没成立（参数存错/条件写反） |
| 都正常但结果不对 | 裁剪逻辑本身有问题 |

## 7.18 PyCharm 运行了旧文件

现象：改了代码，运行结果还是上一次的。

看输出第一行的路径：

```
"C:\...\python.exe" "C:\...\script.py"     ← 跑的是 script.py，不是你正在编辑的文件
```

**原因**：PyCharm 的绿色三角和 `Shift+F10` 执行的是**运行配置下拉框里当前选中的那个**，与你正在编辑哪个文件无关。

解决：

| 方式 | 操作 |
|---|---|
| 推荐 | 编辑区右键 → `运行 '当前文件名'` |
| 快捷键 | `Ctrl + Shift + F10`（运行当前光标所在文件） |
| 手动 | 右上角下拉框切换配置 |

`Shift + F10` 是"运行上次的配置"，`Ctrl + Shift + F10` 是"运行当前文件"——**记住这个区别能省很多时间**。

---

# 八、可复制模板库

> 这些不用背，用的时候复制。但每个模板下面的 ⚠️ 是机制，必须理解。

## 8.1 路径三件套

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
```

⚠️ 每个会读写文件的脚本都要带上这三行，不能省。`exist_ok=True` 保证重复运行不报错，开销几乎为零。
⚠️ `.resolve()` 不能省——它消除 `__file__` 是相对路径带来的不确定性。

## 8.2 logging 标准配置

```python
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(DATA_DIR / "app.log", encoding="utf-8", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)
```

⚠️ `basicConfig` 必须在第一条日志之前，否则**静默失效不报错**。位置：紧跟 import。
⚠️ `FileHandler` 必须带 `encoding="utf-8"`，否则中文乱码。
⚠️ 生产环境把 `mode="w"` 去掉（默认追加），历史日志是排查线上问题的唯一依据。
⚠️ 库和模块**永远不要调 basicConfig**，那是应用程序入口的事。

## 8.3 安全读取 JSON

```python
import json
from pathlib import Path


def safe_load_json(path: Path) -> dict:
    """读取 JSON 文件，失败时返回空字典并说明原因。"""
    if not path.exists():
        print(f"文件不存在: {path}")
        return {}

    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"JSON 格式错误 [{path.name}]: {e}")
        return {}
```

⚠️ 两种失败原因分开处理，报错信息才能指向真正的问题。
⚠️ `{e}` 会给出精确到行列的位置，一定要带上。

## 8.4 写 JSON 文件

```python
config_file.write_text(
    json.dumps(data, ensure_ascii=False, indent=2),
    encoding="utf-8"
)
```

⚠️ 两个编码参数都要带：`ensure_ascii=False` 管中文显示，`encoding="utf-8"` 管文件编码。

## 8.5 异常类三件套

```python
class ToolError(Exception):
    """本模块所有错误的基类"""


class ToolNotFoundError(ToolError):
    """找不到目标"""


class ToolExecutionError(ToolError):
    """执行失败"""
```

⚠️ 定义在文件顶层，不要嵌套进业务类里。
⚠️ 继承分层的价值：`except ToolError` 能一次接住所有子类。

## 8.6 .env 加载与校验

```python
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR.parent / ".env"        # 按实际层级调整

if not ENV_FILE.exists():
    raise FileNotFoundError(
        f"未找到配置文件: {ENV_FILE}\n请复制 .env.example 为 .env 并填入配置"
    )

load_dotenv(ENV_FILE)


def check_required_config() -> None:
    required = ["API_KEY", "MODEL_NAME"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise ValueError(f"缺少必需的配置项: {missing}\n请检查: {ENV_FILE}")


check_required_config()

max_turns = int(os.getenv("MAX_TURNS", "10"))
temperature = float(os.getenv("TEMPERATURE", "0.7"))
debug = os.getenv("DEBUG", "false").lower() == "true"
api_key = os.getenv("API_KEY")

print(f"API_KEY: {api_key[:10]}...")      # 永远不要完整打印密钥
```

⚠️ `load_dotenv` 必须在所有 `getenv` 之前。
⚠️ 环境变量全是字符串，数字要 `int()`/`float()`，布尔值**绝不能用 `bool()`**。
⚠️ 打印密钥时用切片截断。

## 8.7 .gitignore

```
# 环境变量（含密钥，绝不提交）
.env

# 虚拟环境
.venv/
venv/

# Python 缓存
__pycache__/
*.pyc

# IDE 配置
.idea/
.vscode/

# 日志和数据
*.log
data/
```

⚠️ **项目建好的第一件事就写它**——对已经被 Git 追踪的文件无效。
⚠️ `.gitignore` 和 `.env.example` 要提交，`.env` 不提交。

## 8.8 pip 国内镜像

```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

⚠️ 一次配置永久生效。报 `from versions: none` 时几乎都是网络问题，不是包不存在。

---

# 九、本周形成的规则清单

这些是**必须记住**的，和上一章"复制就行"的模板不同。判断标准：**记错了会不会造成实际损失？**

## 数据与对象

1. 可变对象（list/dict/set）绝不做默认参数，用 `None` 占位后在函数体内创建
2. 可变对象绝不做类属性，一律在 `__init__` 里初始化
3. 想改类属性必须用 `类名.属性名`，`self.属性名` 会在实例上新建属性
4. 和 `None` 比较用 `is`，不用 `==`
5. `__init__` 只准备空容器，不装东西；只做数据准备，不做耗时操作

## 方法与调用

6. 方法要调用（加括号），属性才能赋值；属性名不能和方法名重名
7. 判断方法要不要参数：问"这个信息 self 身上有吗"
8. 定义方法忘写 `self` 的症状是 `takes 0 positional arguments but 1 was given`
9. `return` 一执行函数立刻退出，后面的代码永远到不了

## 异常

10. 只捕获你知道怎么处理的异常；处理不了就让它抛，崩在第一现场
11. 绝不裸 `except:`，它会吞掉拼写错误和 Ctrl+C
12. 要捕获某异常，try 块里必须有代码抛出它
13. 只有 `raise` 能中断流程，`print` 和 `logger` 都不能
14. `-> None` 只有真不返回值时才写
15. `logger.exception` 只在 except 块里用

## 路径与编码

16. 路径从 `Path(__file__).resolve().parent` 出发算，不用相对路径
17. 读写文本一律 `encoding="utf-8"`
18. `mkdir` 一律带 `parents=True, exist_ok=True`
19. JSON 有中文一律 `ensure_ascii=False`

## 配置与顺序

20. 配置在前，使用在后：`basicConfig` → 日志；`load_dotenv` → `getenv`；`BASE_DIR` → 拼路径
21. 环境变量全是字符串，布尔值绝不用 `bool()` 转
22. `.gitignore` 在写第一行代码之前就建好
23. 密钥绝不硬编码，绝不完整打印

## 信息质量

24. 日志和错误信息必须带上触发它的具体值
25. 好的错误信息还要告诉用户怎么解决
26. 给模型看的错误文本必须显式包含根因（`from e` 的异常链模型读不到）

## 认知

27. 类型注解在**编写时**生效，运行时完全无效——别拿运行报错验证注解
28. 写错的注解比不写更糟，它会主动误导人
29. 写类之前先画数据结构（用注释画），这一步不能跳
30. 任何有裁剪/过滤/去重逻辑的代码，必须构造一个必然触发它的测试用例

---

# 十、独立编程实战

本周从空白文件独立完成了两个类，都是后面真正会用到的组件。

## 10.1 ToolRegistry：工具注册表

Agent 需要管理一批工具（函数）。模型说"我要调用 get_weather"，代码得能根据这个名字找到对应的函数并执行。

**数据结构**：

```python
# self.tools 的结构：
# {
#     "工具名": {"func": 函数对象, "description": "描述文字"},
# }
```

**核心方法**：

```python
def register(self, name, func, description) -> None:
    if name in self.tools:
        print(f"[警告] 工具 {name} 已存在，将被覆盖")
    self.tools[name] = {"func": func, "description": description}


def call(self, name: str, *args):
    if name not in self.tools:
        raise ToolNotFoundError(f"工具不存在: {name}，已注册: {self.list_names()}")
        # 放在 try 【外面】—— 这不是"执行失败"，性质不同。
        # 放进 try 的话会被下面的 except Exception 捕获，包装成错误的类型。

    try:
        result = self.tools[name]["func"](*args)
        logger.info(f"调用工具 {name}, 参数={args}, 结果={result}")
        return result
    except Exception as e:
        logger.exception(f"工具 {name} 执行失败, 参数={args}")
        raise ToolExecutionError(
            f"工具 {name} 执行失败: {type(e).__name__}: {e}"
        ) from e
```

**`*args` 的用法**：函数内部它是一个元组，调用另一个函数时用 `func(*args)` 展开传进去。

```python
reg.call("add", 3, 5)          # args = (3, 5)
reg.call("greet", "张三")       # args = ('张三',)  ← 单元素元组的尾逗号是语法要求
```

**最关键的一行**：

```python
return self.tools[name]["func"](*args)
```

从左往右读：取内层字典 → 取出函数 → 加括号调用 → 展开参数。**函数存在变量里，取出来加个括号就能执行**——这是 Function Calling 的地基。

**实测输出**：

```
工具数量: 2
工具列表: ['add', 'greet']
add 在吗: True
xxx 在吗: False
调用 add: 8
调用 greet: 你好，张三
schema: [{'name': 'add', 'description': '两数相加'}, {'name': 'greet', 'description': '打招呼'}]
取不存在的: None
[警告] 工具 add 已存在，将被覆盖
清空schema后工具数量: 2
捕获到异常: 工具不存在: 不存在的工具，已注册: ['add', 'greet']
```

加上异常处理后：

```
8
5.0
执行出错: 工具 divide 执行失败: ZeroDivisionError: division by zero
工具不存在: 不存在，已注册: ['add', 'divide']
捕获 ToolNotFoundError: 工具不存在: 不存在，已注册: ['add', 'divide']
捕获 ToolExecutionError: 工具 divide 执行失败: ZeroDivisionError: division by zero
原始异常: ZeroDivisionError
```

最后一行证明 `from e` 的异常链生效了——`e.__cause__` 能取到原始异常。

## 10.2 TokenCounter：token 计数器

### 为什么需要它

Token 是模型处理文本的最小单位。**英文约 1 token ≈ 4 字符，中文约 1 汉字 ≈ 1~1.5 token**（没有精确公式，每个模型的 tokenizer 不同）。

API 按 token 计费，输入输出价格不同。而 Agent 的问题在于：

```
第 1 轮：发 100 token
第 2 轮：发 100 + 上一轮问答 = 300 token
第 3 轮：发 300 + 这一轮问答 = 600 token
...
```

**因为模型没有记忆，每轮都要把完整历史重发一遍，成本是平方级增长的。**

这正是 `Conversation._trim()` 存在的原因。而且模型有上下文窗口硬上限，超了直接报错，不是截断继续。

### 数据结构选型

两个方案：

| 方案 | 结构 | 优势 | 代价 |
|---|---|---|---|
| A | 存原始记录列表 | 明细保留，以后想加任何分析都行 | 每次统计要遍历 |
| B | 存累加值字典 | 计算快 | 明细丢失，回不去了 |

**我选了 A**，理由是：**先存原始数据、需要时再聚合，是数据处理的通用原则。** 聚合是不可逆的，一旦揉成总数，"平均每次消耗""单次最贵的调用""最近 n 次"这些分析全做不了。

代价是每次统计要遍历，但几十条记录完全无所谓。真到几百万条了再加缓存。

```python
# self.records 的结构：
# [
#     {"model": "deepseek-chat", "prompt_tokens": 100, "completion_tokens": 50},
#     {"model": "gpt-4", "prompt_tokens": 500, "completion_tokens": 300},
# ]
```

### 分组累加的惯用模式

```python
def by_model(self) -> dict[str, int]:
    result = {}

    for record in self.records:
        model = record["model"]
        tokens = record["prompt_tokens"] + record["completion_tokens"]
        result[model] = result.get(model, 0) + tokens
        #               └────────┬────────┘   └──┬──┘
        #            已累计的值（没有则0）      本次的

    return result
```

`.get(键, 默认值)` 在这里的作用是**避免判断键存不存在**。不用它的话要写：

```python
if model in result:
    result[model] = result[model] + tokens
else:
    result[model] = tokens
```

功能一样但啰嗦。

### 校验放在最前面

```python
def record(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    if prompt_tokens < 0:
        raise ValueError(f"prompt_tokens 不能为负: {prompt_tokens}")
    if completion_tokens < 0:
        raise ValueError(f"completion_tokens 不能为负: {completion_tokens}")

    self.records.append({...})
```

**两个校验分开写**，报错信息才能精确指出是哪个参数。合并成一个 if 的话，用户只知道"有负数"。

**顺序很关键**：校验必须在 append 之前。先 append 再校验的话，非法数据已经污染了内部状态，就算 raise 了也来不及。

### 查询方法不记日志

- `record()` 记 INFO ✅（有新数据进来，状态变了）
- 校验失败记 WARNING ✅（异常情况）
- `total()`、`by_model()`、`top_model()` 不记 ❌（只是查询，记了会淹没真正重要的日志）

**日志应该记状态变化和异常，不记"有人查询了一下"。**

### 实测输出

```
16:37:34 [INFO] __main__ - 使用模型:deepseek-chat,发送token消耗: 100,回答token消耗50
16:37:34 [INFO] __main__ - 使用模型:deepseek-chat,发送token消耗: 200,回答token消耗80
16:37:34 [INFO] __main__ - 使用模型:gpt-4,发送token消耗: 500,回答token消耗300
总数: 1230
分模型: {'deepseek-chat': 430, 'gpt-4': 800}
最贵: gpt-4
记录数: 3
============================
总消耗: 1230 tokens
调用次数: 3
--- 分模型 ---
  deepseek-chat: 430
  gpt-4: 800
消耗最多: gpt-4
============================
空计数器: None
捕获: prompt_tokens不能为负数：-1
```

`430` 是关键——两条 deepseek-chat 记录（150 + 280）正确合并了，说明累加模式写对了。

---

# 十一、写在最后

## 这周最大的收获不是语法

而是三个认知：

**① 先画数据结构，再写代码。** 我两次卡在写不出方法，根源都是跳过了这一步。数据结构定了，方法无非是对它做增删改查。

**② 让错误尽早暴露，且报错信息说人话。** 这是工程代码和玩具代码的分水岭。整周反复出现的模式是：静默失败 → 错误在很远的地方爆发 → 排查方向完全跑偏。

**③ 区分"看得懂"和"写得出"。** 看代码调用的是识别能力，写代码需要的是提取能力。唯一的解法是从空白文件硬写。

## 遇到不会的函数怎么办

不要问"我该用什么函数"，问"**我要对什么数据做什么动作**"。把这句话说清楚，函数名基本就出来了。

| 一句话描述 | 搜索词 |
|---|---|
| 我要同时拿到字典的键和值 | `python 字典 同时遍历键和值` → `.items()` |
| 我要按名字取值，没有就返回默认 | `python 字典 取值 默认值` → `.get()` |
| 我要找字典里值最大的键 | `python 字典 值最大的键` → `max(d, key=d.get)` |

**三个动作，按顺序用**：

1. 在 IDE 里**打点看提示**——变量后面敲个 `.`，所有可用方法都会弹出来
2. 搜"python + 数据类型 + 你要做的事"
3. 问人时只问"有没有现成方法"，不要直接要代码

## 下周计划

第 2 周：Git + HTTP + 异步。

- Git 的增删改查、分支、冲突解决
- HTTP 基础与 `httpx`
- `async/await`——Agent 要并发调多个工具、流式返回 token，全靠它

---

*本文是我从零学 AI Agent 开发的第 1 周记录，持续更新中。*
