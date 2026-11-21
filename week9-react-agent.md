# 第 9 周技术总结：纯手写 ReAct Agent 与三道安全护栏工程化实践

> **阶段三收官 & 阶段四启航**：不依赖任何高层框架，基于 DeepSeek V4.1 Flash（OpenAI 兼容协议）从零构建 `ToolRegistry` 工具注册中心、ReAct 推理-行动闭环主循环，以及覆盖最大轮次、死循环与单步超时的三道生产级安全熔断机制。

| 元信息维度 | 本周具体配置与归档信息 |
| :--- | :--- |
| **学习阶段与周期** | 第 9 周（完成前 8 周工程地基、Function Calling 与 RAG 项目上线后，正式切入 Agent 核心引擎开发） |
| **核心关键词** | ReAct 范式、`ToolRegistry` 工具注册表、`safe_call` 异常沙箱、`Observation` 自我纠错、三道安全护栏、Trace 可观测日志 |
| **模型与技术栈** | Python 3.x、OpenAI SDK（兼容协议）、DeepSeek V4.1 Flash、`concurrent.futures.ThreadPoolExecutor`、`json` |
| **代码仓库地址** | [https://github.com/Ruiwen-ZHANG/ai-agent-learning](https://github.com/Ruiwen-ZHANG/ai-agent-learning)（目录：`week9/`） |
| **本周最有分量产出** | 1) `week9/tools.py`（自动化 Schema 生成与异常隔离注册表）<br>2) `week9/react_core.py`（带完整 Trace 日志与三道安全护栏的 `ReActAgent` 主循环）<br>3) 异常自主恢复实测（`FileNotFoundError` 自动建档修复）与死循环/超时熔断压测 |

---

## 一、本周概览与核心认知跃迁

前 8 周我们完成了 Python 工程地基、原生 API 调用、单轮 Function Calling 以及 RAG 知识库项目上线。第 9 周的核心目标是捅破 Agent 框架的“黑盒窗户纸”——不借助 LangChain 或 LlamaIndex，纯粹用 Python 原生控制流手写一个完整的 **ReAct（Reasoning + Acting）** 智能体。通过亲手编写状态循环与异常捕获，深刻理解了模型如何从“单次问答机器”进化为“具备自主规划与纠错能力的执行引擎”。

### 1.1 核心认知对比表（从单轮调用到自主闭环）

| 对比维度 | 旧认知 / 传统脚本（Workflow & 单轮调用） | 新认知 / 本周工程实践（纯手写 ReAct Agent） |
| :--- | :--- | :--- |
| **执行路径控制** | 代码里用 `if/else` 提前写死每一步顺序，路径完全固定、可预知。 | 路径无法提前写死；由模型根据上一步的 `Observation` 动态决定下一步调用什么工具或何时结束。 |
| **角色与职责边界** | 误以为大模型直接“运行”了函数或访问了本地文件。 | 模型只负责生成文本与结构化指令（`Thought` + `Action` 决策）；Python 代码负责真正执行函数（`Action` 执行）并将结果包装为 `Observation` 回填。 |
| **异常与报错处理** | 工具函数报错（如 `FileNotFoundError`）直接抛出异常导致整个程序崩溃中断。 | 将工具包裹在 `safe_call` 沙箱中，把报错信息转化为字符串作为 `Observation` 回填给模型，触发模型的“自我纠错”机制。 |
| **循环终止与安全性** | 只靠模型自己决定何时停止，一旦模型陷入执念或外部接口卡死，Token 与线程直接失控。 | 必须在引擎层加装三道硬性安全护栏：最大轮次限制（`max_steps`）、重复动作签名拦截、单工具执行超时熔断。 |
| **架构选型原则** | 觉得 Agent 万能，所有自动化任务都想套用 Agent 循环。 | 步骤固定、每天重复的任务首选确定性 **Workflow**（低延迟、省 Token、零不确定性）；只有动态决策场景才启用 **Agent**。 |

### 1.2 本周小节与产出文件对照表

| 章节模块 | 核心工程主题 | 对应源码 / 产出文件 | 关键验证结果 |
| :--- | :--- | :--- | :--- |
| **第 1 节：工具注册中心** | `ToolRegistry` 设计、OpenAI/DeepSeek Schema 导出与 `safe_call` 异常隔离 | `week9/tools.py`<br>`requirements.txt` | 支持一键注册工具并自动转换为标准 `tools` JSON 列表，异常零崩溃返回字符串。 |
| **第 2 节：ReAct 主循环** | `Thought` / `Action` / `Observation` 状态机、`messages` 上下文追加与 Trace 日志 | `week9/react_core.py` | 完成多步工具串联调用；在读取不存在文件触发 `FileNotFoundError` 时自主新建文件修复。 |
| **第 3 节：三道安全护栏** | `max_steps` 轮次熔断、规范化 JSON 签名防死循环、`ThreadPoolExecutor` 30s 超时 | `week9/react_core.py` | 成功拦截 `check_ticket` 死循环与 `slow_query` 超时阻塞，并输出合理兜底 `Final Answer`。 |
| **第 4 节：理论辨析复盘** | ReAct 职责分工、死循环根因与防护、Agent vs Workflow 边界三问 | 本周学习问答复盘 | 建立清晰的架构选型直觉，避免过度设计。 |

---

## 二、分章拆解（原理 → 代码 → 实测）

### 2.1 `ToolRegistry` 工具注册与安全隔离层（`week9/tools.py`）

* **直觉比方与设计原理**：如果把 ReAct Agent 比作一家公司，大模型就是坐在办公室里的“总经理”，只负责看报告、做决策；而本地 Python 函数就是一线“执行专员”。总经理看不懂 Python 源码，必须有一份标准化的《岗位说明书》（Function Calling JSON Schema）；同时，一线专员外出办事难免遇到意外（文件不存在、参数传错、网络超时），不能直接把天捅破，而要把失败原因写成书面汇报交回给总经理。`ToolRegistry` 的核心使命就是充当这份“标准化注册表 + 异常防爆盾”。
  * **统一注册（`register`）**：集中维护工具名称（`name`）、实际可调用函数（`func`）、自然语言描述（`description`）以及参数 JSON Schema（`parameters`）。
  * **协议适配（`to_schema`）**：将内部存储的元信息自动组装为符合 OpenAI / DeepSeek 接口规范的 `tools` 列表，解耦业务函数与模型协议。
  * **安全沙箱（`safe_call` / `call`）**：通过 `safe_call` 统一捕获所有执行期异常（如 `FileNotFoundError`、`TypeError` 等），将其格式化为 `"Error: <异常类型> - <详情>"` 字符串返回，确保主循环永不因工具报错而崩溃。

```python
# 核心源码：week9/tools.py — ToolRegistry 注册表与安全调用封装
import json
import os
import time
from typing import Any, Callable, Dict, List


class ToolRegistry:
    """工具注册中心：负责工具元数据管理、OpenAI/DeepSeek Schema 导出与安全沙箱执行"""

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, func: Callable, description: str, parameters: Dict[str, Any]):
        """注册单个工具及其 JSON Schema 参数规范"""
        self._tools[name] = {
            "name": name,
            "func": func,
            "description": description,
            "parameters": parameters,
        }

    def to_schema(self) -> List[Dict[str, Any]]:
        """导出符合 OpenAI / DeepSeek Function Calling 标准的 tools 列表"""
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            })
        return schemas

    def safe_call(self, name: str, arguments: Dict[str, Any]) -> str:
        """安全执行工具：捕获一切异常并转化为可读字符串，供模型作为 Observation 自我纠错"""
        if name not in self._tools:
            return f"Error: 未找到名为 '{name}' 的注册工具，请检查工具名称。"
        func = self._tools[name]["func"]
        try:
            result = func(**arguments)
            return str(result)
        except Exception as e:
            return f"Error: 工具 '{name}' 执行失败 ({type(e).__name__}: {str(e)})"

    def call(self, name: str, raw_arguments: str) -> str:
        """统一分发入口：先安全解析 JSON 参数，再调用 safe_call"""
        try:
            args = json.loads(raw_arguments) if raw_arguments else {}
            if not isinstance(args, dict):
                return f"Error: 工具参数必须是 JSON 对象，当前解析类型为 {type(args).__name__}"
        except json.JSONDecodeError as e:
            return f"Error: 参数 JSON 解析失败 ({str(e)})，请输出合法的 JSON 格式参数。"
        return self.safe_call(name, args)
```

> **配套测试工具说明**：在基础工具集中，我们配套编写了文件读写工具（`read_file`、`write_file`）用于验证异常自我纠错，以及专用压测工具（`check_ticket` 模拟恒定返回“排队中”诱发死循环、`slow_query` 模拟 `time.sleep(35)` 诱发单步超时），为后续三道护栏验证做好充分准备。

---

### 2.2 ReAct 主循环与异常自我纠错实测（`week9/react_core.py`）

* **原理拆解**：ReAct 的本质是一个围绕 `messages` 历史列表不断追加上下文的状态机循环。每一轮迭代（Step）都遵循严格的四步流转：
  1. 将完整对话历史与 `tools` Schema 发给 DeepSeek V4.1 Flash；
  2. 若模型未发起 `tool_calls`，说明推理完成，直接提取最终回复作为 `Final Answer` 跳出循环；
  3. 若模型返回了 `tool_calls`，则先将包含 `tool_calls` 的 `assistant` 消息原封不动追加进 `messages`；
  4. 逐个执行工具，并将结果以 `role='tool'`、绑定对应 `tool_call_id` 的形式回填进 `messages`，进入下一轮思考。

```python
# 核心源码：week9/react_core.py — ReActAgent 主循环与三道安全护栏实现
import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List
from openai import OpenAI
from tools import ToolRegistry


class ReActAgent:
    """纯手写 ReAct Agent：集成 Trace 日志与三道生产级安全护栏"""

    def __init__(
        self,
        registry: ToolRegistry,
        model: str = "deepseek-chat",  # 对应 DeepSeek V4.1 Flash 兼容端点
        max_steps: int = 8,
        tool_timeout: int = 30,
        repeat_threshold: int = 3,
    ):
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        self.registry = registry
        self.model = model
        self.max_steps = max_steps                # 护栏 1：最大轮次限制
        self.tool_timeout = tool_timeout          # 护栏 3：单工具执行超时（秒）
        self.repeat_threshold = repeat_threshold  # 护栏 2：连续重复动作拦截阈值

    def _normalize_action(self, tool_name: str, raw_args: str) -> str:
        """规范化动作签名：消除空格与键顺序差异，防止死循环检测被绕过"""
        try:
            parsed = json.loads(raw_args) if raw_args else {}
            norm_args = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        except Exception:
            norm_args = str(raw_args).strip()
        return f"{tool_name}::{norm_args}"

    def _execute_with_timeout(self, tool_name: str, raw_args: str) -> str:
        """使用 ThreadPoolExecutor 对单次工具调用实施超时控制"""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.registry.call, tool_name, raw_args)
            try:
                return future.result(timeout=self.tool_timeout)
            except FuturesTimeoutError:
                return (
                    f"Error: 工具 '{tool_name}' 执行超时（超过 {self.tool_timeout} 秒已强制中断）。"
                    "请勿继续等待该工具，尝试换用其他方法或直接给出当前总结。"
                )

    def _fallback_summary(self, messages: List[Dict[str, Any]], reason: str) -> str:
        """触发护栏熔断时，请求模型基于已有上下文生成兜底 Final Answer"""
        messages.append({
            "role": "user",
            "content": f"[系统安全护栏触发：{reason}] 请停止调用任何工具，直接根据目前已掌握的信息给出最终总结与建议。"
        })
        resp = self.client.chat.completions.create(model=self.model, messages=messages)
        return resp.choices[0].message.content or f"任务因安全护栏终止：{reason}"

    def run(self, user_query: str) -> str:
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是一个严谨的智能助手，遵循 ReAct（思考-行动-观察）模式解决问题。"
                    "每次调用工具前请明确推理目的；若工具返回 Error，请分析报错原因并尝试自主修复。"
                ),
            },
            {"role": "user", "content": user_query},
        ]
        action_history: List[str] = []

        for step in range(1, self.max_steps + 1):
            print(f"\n--- [Step {step}/{self.max_steps}] ---")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.registry.to_schema(),
                tool_choice="auto",
            )
            msg = response.choices[0].message

            if msg.content:
                print(f"[Thought]: {msg.content}")

            # 无工具调用 -> 任务完成，输出 Final Answer
            if not msg.tool_calls:
                print(f"[Final Answer]: {msg.content}")
                return msg.content or ""

            # 必须先将包含 tool_calls 的 assistant 消息写入上下文
            messages.append(msg.model_dump(exclude_none=True))

            for tool_call in msg.tool_calls:
                t_name = tool_call.function.name
                t_args = tool_call.function.arguments
                print(f"[Action]: 调用工具 {t_name}({t_args})")

                # 护栏 2：死循环检测（比对最近 repeat_threshold 次规范化签名）
                sig = self._normalize_action(t_name, t_args)
                action_history.append(sig)
                if (
                    len(action_history) >= self.repeat_threshold
                    and len(set(action_history[-self.repeat_threshold:])) == 1
                ):
                    reason = f"检测到连续 {self.repeat_threshold} 次重复相同动作 ({sig})，判定陷入死循环"
                    print(f"[Guardrail Triggered]: {reason}")
                    return self._fallback_summary(messages, reason)

                # 护栏 3：带超时隔离的工具执行
                observation = self._execute_with_timeout(t_name, t_args)
                print(f"[Observation]: {observation}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": observation,
                })

        # 护栏 1：达到 max_steps 仍未收敛 -> 触发最大轮次熔断
        reason = f"已达到最大允许迭代轮次 max_steps={self.max_steps}"
        print(f"[Guardrail Triggered]: {reason}")
        return self._fallback_summary(messages, reason)
```

#### 实测一：`FileNotFoundError` 异常处理与 Agent 自主纠错闭环

向 Agent 下达指令：“请读取 `not_exist.txt` 的内容；如果文件不存在，请帮我创建该文件并写入‘初始化完成’”。实测控制台完整捕捉到了异常捕获与模型的二次决策过程：

```text
--- [Step 1/8] ---
[Thought]: 需要先尝试读取 not_exist.txt 的内容，确认文件是否存在。
[Action]: 调用工具 read_file({"filepath": "not_exist.txt"})
[Observation]: Error: 工具 'read_file' 执行失败 (FileNotFoundError: [Errno 2] No such file or directory: 'not_exist.txt')

--- [Step 2/8] ---
[Thought]: 观察结果显示 not_exist.txt 不存在（触发了 FileNotFoundError）。根据任务要求，我现在调用 write_file 创建该文件并写入“初始化完成”。
[Action]: 调用工具 write_file({"filepath": "not_exist.txt", "content": "初始化完成"})
[Observation]: 成功写入 5 个字符到 not_exist.txt

--- [Step 3/8] ---
[Final Answer]: 已检测到 not_exist.txt 原本不存在，现已为您自动创建该文件并成功写入内容“初始化完成”。
```

---

### 2.3 三道安全护栏与生产级鲁棒性压测

在纯手写 Agent 中，最危险的工程事故不是“答错”，而是“失控”——模型因为外部环境无变化而无限重试，或者某个底层工具发生网络挂起导致整个进程永久卡死。本周我们在 `react_core.py` 中构筑了三道纵深防御护栏，并针对死循环（`check_ticket`）与单步超时（`slow_query`）进行了专项压测：

1. **第一道护栏（最大轮次熔断 `max_steps`）**：在 `for step in range(1, self.max_steps + 1)` 外层设定硬性步数天花板（默认 8 轮），耗尽步数仍未给出答案时立即跳出循环并请求模型生成兜底总结。
2. **第二道护栏（重复动作死循环拦截）**：维护 `action_history` 列表，使用 `json.dumps(parsed, sort_keys=True)` 对工具名与参数做规范化序列化。一旦检测到最近 3 次动作签名完全一致，立即判定为原地打转并强制熔断。
3. **第三道护栏（单工具执行超时控制）**：通过 `ThreadPoolExecutor` 提交工具任务并使用 `future.result(timeout=30)` 限时等待，超时后立刻释放控制权并向模型回填超时提示，防止主循环无限阻塞。

```text
# 测试 A：死循环拦截压测（任务：持续查询工单 T-1001 状态直到变为已完成）
--- [Step 1/8] ---
[Action]: 调用工具 check_ticket({"ticket_id": "T-1001"})
[Observation]: 工单 T-1001 当前状态：处理中（排队第 5 位）

--- [Step 2/8] ---
[Action]: 调用工具 check_ticket({"ticket_id": "T-1001"})
[Observation]: 工单 T-1001 当前状态：处理中（排队第 5 位）

--- [Step 3/8] ---
[Action]: 调用工具 check_ticket({ "ticket_id" : "T-1001" })
[Guardrail Triggered]: 检测到连续 3 次重复相同动作 (check_ticket::{"ticket_id": "T-1001"})，判定陷入死循环
[Final Answer]: 工单 T-1001 目前仍处于“处理中（排队第 5 位）”状态，由于短时间内状态未发生变化，系统已自动停止重复轮询。建议您稍后再试。

# 测试 B：单步执行超时压测（任务：执行慢查询 slow_query）
--- [Step 1/8] ---
[Action]: 调用工具 slow_query({"query": "SELECT * FROM large_logs"})
[Observation]: Error: 工具 'slow_query' 执行失败/超时（超过 30 秒已强制中断）。请勿继续等待该工具，尝试换用其他方法或直接给出当前总结。

--- [Step 2/8] ---
[Final Answer]: 慢查询工具执行超过 30 秒已触发系统超时保护并安全中断，建议缩小查询时间范围或添加索引条件后重试。
```

---

## 三、典型错误合集（按根因分类）

本周在从零手写 Agent 的调试过程中，踩中了三类极具代表性的工程坑点。以下按故障根因归类复盘，保留真实报错线索与修复对照。

### 3.1 根因一：结构化参数解析与动作签名未规范化（`JSONDecodeError` & 签名漏判）

* **真实报错与审阅线索**：
  1. 报错信息：`json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)`
  2. 逻辑漏判：模型第 1 次输出 `'{"ticket_id":"T-1001"}'`, 第 2 次输出 `'{"ticket_id": "T-1001"}'`, 直接字符串比对导致死循环检测失效！
* **根因剖析**：模型生成的 `arguments` 本质是一段纯文本字符串，既可能因为偶发语法瑕疵导致 `json.loads` 崩溃，也可能因为空格数量、字典键顺序不同（如 `{"a":1, "b":2}` vs `{"b":2, "a":1}`）导致语义完全相同的调用生成不同的原始字符串。

```python
# ❌ 错误示范：直接裸调 json.loads 且用原始字符串做重复签名比对
args = json.loads(tool_call.function.arguments)  # 一旦模型输出非法 JSON 直接崩溃
sig = f"{tool_call.function.name}:{tool_call.function.arguments}"  # 空格/键序不同即漏判

# ✅ 正确写法：安全解析捕获 JSONDecodeError + sort_keys=True 规范化序列化
try:
    parsed = json.loads(raw_args) if raw_args else {}
    norm_args = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
except json.JSONDecodeError as e:
    return f"Error: 参数 JSON 解析失败 ({str(e)})，请输出合法的 JSON 格式参数。"
sig = f"{tool_name}::{norm_args}"
```

### 3.2 根因二：工具执行异常未做沙箱隔离导致主循环崩溃（`FileNotFoundError` / `TypeError`）

* **真实报错与审阅线索**：
  1. 报错信息 1：`FileNotFoundError: [Errno 2] No such file or directory: 'not_exist.txt'`
  2. 报错信息 2：`TypeError: read_file() missing 1 required positional argument: 'filepath'`（模型幻觉传参名错误导致）
* **根因剖析**：在传统编程中，异常抛出是为了中断错误流程；但在 Agent 架构中，工具执行报错恰恰是极其宝贵的环境反馈信号。如果不在 `ToolRegistry` 层捕获 `Exception`，程序直接抛出 Traceback 退出，模型根本没有机会看到错误信息并修正参数或切换备选方案。

```python
# ❌ 错误示范：在 ReAct 主循环中直接解包调用工具函数
result = tool_func(**args)  # 遇到 FileNotFoundError 或 TypeError 整个进程直接退出

# ✅ 正确写法：在 ToolRegistry.safe_call 中全量捕获异常并转化为 Observation 字符串
try:
    result = func(**arguments)
    return str(result)
except Exception as e:
    return f"Error: 工具 '{name}' 执行失败 ({type(e).__name__}: {str(e)})"
```

### 3.3 根因三：缺乏边界熔断与超时控制导致死循环耗尽 Token 与主线程阻塞

* **真实报错与审阅线索**：
  1. 死循环现象：在未加护栏前测试 `check_ticket`，Agent 连续请求了十几轮完全相同的查询，不断消耗 API 额度却毫无进展。
  2. 线程挂起现象：调用 `slow_query` 时，主线程同步阻塞等待超过半分钟无任何响应，日志停滞。
* **根因剖析**：大模型本身没有“时间流逝”概念，也缺乏全局状态记忆，容易在外部状态未改变时陷入局部最优重试；同时 Python 同步函数调用默认没有超时限制。必须通过 `max_steps`、最近 N 次 `action_history` 校验以及 `ThreadPoolExecutor` 超时控制形成三层硬性边界。

```python
# ❌ 错误示范：使用 while True 无上限循环且同步直调耗时工具
while True:
    observation = registry.call(t_name, t_args)  # 既无步数上限，也无超时与重复动作检测

# ✅ 正确写法：有界 for 循环 + 最近 3 次动作签名比对 + ThreadPoolExecutor 超时中断
for step in range(1, self.max_steps + 1):
    # ... 检测 action_history[-3:] 是否全部相同 ...
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(self.registry.call, t_name, t_args)
        observation = future.result(timeout=self.tool_timeout)
```

### 3.4 本周典型错误模式统计表

| 错误根因类别 | 典型异常 / 现象 | 发生层级 | 工程化修复方案 |
| :--- | :--- | :--- | :--- |
| **输入/参数规范化缺失** | `JSONDecodeError`、空格/键序差异导致重复检测漏判 | 参数反序列化层 | 捕获 `JSONDecodeError` 回填 Observation；用 `sort_keys=True` 生成唯一签名。 |
| **异常边界未隔离** | `FileNotFoundError`、`TypeError` 导致主程序直接崩溃 | `ToolRegistry` 执行层 | 统一封装 `safe_call`，将所有 `Exception` 转为 `"Error: ..."` 字符串回填模型。 |
| **控制流与资源无上限** | 重复轮询死循环、慢工具阻塞主进程 | `ReActAgent` 调度层 | 加装 `max_steps`、`action_history` 重复拦截、`ThreadPoolExecutor` 30s 超时熔断。 |

---

## 四、本周自检清单（CheckList）

结合本周代码落地与三道核心理论辨析题复盘，完成以下自检项确认：

- [x] **架构理解**：能清晰界定 ReAct 三要素分工——`Thought` 由模型推理产生；`Action` 分为“决策（模型输出工具名与参数）”与“执行（Python 代码运行函数）”；`Observation` 由代码封装执行结果并回填进 `messages`。
- [x] **工具注册表**：独立完成 `week9/tools.py`，实现 `ToolRegistry` 的动态注册、标准 Function Calling Schema 导出与 `safe_call` 异常隔离。
- [x] **主循环与消息协议**：正确处理 `assistant` 的 `tool_calls` 消息留存与 `role='tool'`（携带 `tool_call_id`）的回填顺序，完整打印 `Thought` / `Action` / `Observation` Trace 日志。
- [x] **异常自主恢复**：实测 `FileNotFoundError` 异常回填闭环，验证模型能够读懂报错信息并自主调用 `write_file` 创建缺失文件。
- [x] **三道安全护栏**：在 `week9/react_core.py` 中落地 `max_steps` 最大轮次限制、基于 `sort_keys=True` 的最近 3 次重复动作拦截、以及基于 `ThreadPoolExecutor` 的 30 秒单步超时熔断，并实现熔断后的兜底 `Final Answer` 生成。
- [x] **工程选型判断**：明确 **Workflow**（步骤固定、重复执行、低成本高确定性）与 **Agent**（路径不可预知、依赖中间 `Observation` 动态决策）的适用边界。

---

## 五、附录

### 附录 A：ReAct Agent 核心设计速查表

| 核心组件 / 护栏 | 所在文件与方法 | 核心职责与设计要点 | 关键参数 / 阈值 |
| :--- | :--- | :--- | :--- |
| **ToolRegistry** | `week9/tools.py`<br>`register()` / `to_schema()` | 管理本地 Python 函数元数据并转换为 OpenAI/DeepSeek 兼容的 `tools` JSON Schema。 | `tools: List[Dict]` |
| **安全执行沙箱** | `week9/tools.py`<br>`call()` / `safe_call()` | 拦截 `JSONDecodeError` 及一切工具运行时异常，转为 `Error` 字符串返回。 | 返回类型恒为 `str` |
| **ReAct 状态循环** | `week9/react_core.py`<br>`ReActAgent.run()` | 维护 `messages` 上下文，驱动 `Thought → Action → Observation` 多轮流转。 | `model = DeepSeek V4.1 Flash` |
| **护栏 1：轮次熔断** | `week9/react_core.py`<br>`for step in range(...)` | 防止长链条推理无限消耗 Token，耗尽轮次触发 `_fallback_summary`。 | `max_steps = 8` |
| **护栏 2：死循环拦截** | `week9/react_core.py`<br>`_normalize_action()` | 规范化序列化工具名与参数，连续 N 次完全相同即强制熔断。 | `repeat_threshold = 3` |
| **护栏 3：超时控制** | `week9/react_core.py`<br>`_execute_with_timeout()` | 隔离慢工具执行，超时立即抛出 `FuturesTimeoutError` 并回填提示。 | `tool_timeout = 30s` |

### 附录 B：本周新掌握 Python 语法与标准库速查

| 语法 / 标准库模块 | 典型代码示例 | 本周应用场景与工程价值 |
| :--- | :--- | :--- |
| `concurrent.futures`<br>`ThreadPoolExecutor` | `with ThreadPoolExecutor(max_workers=1) as ex:`<br>`    fut = ex.submit(fn, *args)`<br>`    res = fut.result(timeout=30)` | 为同步 Python 工具函数加装非阻塞超时熔断，捕获 `FuturesTimeoutError` 防止主循环永久挂起。 |
| `json.dumps` 规范化<br>`sort_keys=True` | `json.dumps(parsed, sort_keys=True, ensure_ascii=False)` | 消除 JSON 字典键顺序与空格排版差异，为死循环检测生成确定性的唯一动作签名。 |
| Pydantic / SDK<br>`model_dump(exclude_none=True)` | `messages.append(msg.model_dump(exclude_none=True))` | 将 OpenAI SDK 返回的 `ChatCompletionMessage` 对象无损序列化为字典写回对话历史，保留 `tool_calls` 字段。 |
| 异常处理元数据<br>`type(e).__name__` | `f"{type(e).__name__}: {str(e)}"` | 在 `safe_call` 中精准提取异常类名（如 `FileNotFoundError`、`TypeError`）与具体描述，帮助大模型快速定位错误类型。 |

### 附录 C：本周 Git 提交记录（Commit History）

| 提交顺序 | Commit 主题与核心变更摘要 | 涉及文件 |
| :--- | :--- | :--- |
| **Commit 1** | `feat(week9): 实现 ToolRegistry 工具注册中心与基础测试工具集（支持自动导出 Schema 与 safe_call 异常隔离）` | `week9/tools.py`<br>`requirements.txt` |
| **Commit 2** | `feat(week9): 实现基于 DeepSeek V4.1 Flash 的 ReAct 主循环与完整 Trace 日志输出（完成 FileNotFoundError 自主恢复验证）` | `week9/react_core.py` |
| **Commit 3** | `feat(week9): 增加三道安全护栏（max_steps、规范化签名防死循环、ThreadPoolExecutor 30s 超时）与上下文兜底总结机制` | `week9/react_core.py` |

---

## 六、遗留任务与下周预告

* **本周遗留收尾任务**：将本周整理的技术复盘文档（`.docx` 与 `.md`）同步归档至 GitHub 仓库（[https://github.com/Ruiwen-ZHANG/ai-agent-learning](https://github.com/Ruiwen-ZHANG/ai-agent-learning)），并更新仓库根目录 `README.md` 的第 9 周学习进度与目录索引。
* **下周预告（阶段四启航）**：阶段三（Agent 核心引擎原理与手写实现）已圆满收官。第 10 周起将正式迈入 **【阶段四：综合 Agent 实战项目开发】**，把本周手写的 ReAct 引擎与前期积累的 RAG 检索能力深度融合，构建具备多工具协同与复杂任务规划能力的实战级智能体应用。