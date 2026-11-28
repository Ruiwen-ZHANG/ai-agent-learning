# 第 10 周技术复盘：Model Context Protocol (MCP) 协议原理与多 Server 协同实战

> **学习阶段**：AI Agent 工程化进阶（Week 10）  
> **核心技术栈**：Python 3.11 + `mcp==2.3.0` (`MCPServer`) + `openai` (`AsyncOpenAI` / DeepSeek) + `asyncio` + `AsyncExitStack`  
> **代码目录**：`week10/`（`mcp_server.py`、`mcp_client_agent.py`、`kb_mcp_server.py`、`multi_server_demo.py`）

---

## 一、本周学习目标与架构演进

在第 9 周中，我们从零手写了原生的 `ReActAgent` 与本地 `ToolRegistry`，跑通了大模型“思考（Thought）— 行动（Action）— 观察（Observation）”推理闭环与三道工程安全护栏。但在工程扩展时，本地硬编码模式存在明显痛点：每新增一个工具，都必须在 Agent 主程序内部编写实现函数并手写一遍 JSON Schema，工具无法在不同 Agent 宿主间复用。

第 10 周引入 **Model Context Protocol（MCP，模型上下文协议）**，将“工具提供方（MCP Server）”与“智能体宿主（MCP Host / Client）”彻底解耦，实现**外部能力热插拔、自动化 Schema 转译、跨进程生命周期托管与多 Server 故障隔离**。

| 小节 | 主题 | 核心工程目标 | 产出文件 |
| :--- | :--- | :--- | :--- |
| **10.1** | MCP 协议架构与核心原语 | 理解 $M \times N \to M + N$ 演进、Host / Client / Server 职责、JSON-RPC 2.0 与三大原语边界 | 架构原理梳理 |
| **10.2** | 手写标准 MCP Server | 基于 `mcp 2.3.0`（`MCPServer`）暴露自定义 Tools 与 Resource，自动编译 JSON Schema | `week10/mcp_server.py` |
| **10.3** | 编写 MCP Client 桥接器 | 通过 `stdio` 拉起子进程握手，动态转译远程工具注入异步 ReAct 引擎（零手写 Schema） | `week10/mcp_client_agent.py` |
| **10.4** | 多 Server 协同与异常隔离 | 同时挂载多个独立 MCP Server，实现命名空间前缀隔离、单点故障隔离与跨服务排障 | `week10/kb_mcp_server.py`<br>`week10/multi_server_demo.py` |

---

## 二、10.1 MCP 协议核心架构与三大原语

### 2.1 从 $M \times N$ 碎片化到 $M + N$ 标准化生态
* **没有 MCP 之前（$M \times N$）**：$M$ 个 Agent 应用对接 $N$ 个外部数据源，需要编写 $M \times N$ 套胶水代码、参数解析和异常封装。
* **引入 MCP 之后（$M + N$）**：MCP 充当 AI 界的“USB-C 接口”。工具开发者只需按协议实现 **1 份 MCP Server**；Agent 宿主只需实现 **1 份通用的 MCP Client 适配器**，即可即插即用接入所有工具。

```text
┌──────────────────────────────────────────────────────────────────────┐
│                   MCP Host（multi_server_demo.py）                   │
│                                                                      │
│   ┌──────────────┐       ┌───────────────────────────────────────┐   │
│   │ DeepSeek LLM │ ◄───► │ AsyncToolRegistry + AsyncReActAgent   │   │
│   └──────────────┘       └───────────────────┬───────────────────┘   │
│                                              │ 命名空间隔离注册       │
│                          ┌───────────────────┴───────────────────┐   │
│                          ▼                                       ▼   │
│               [ClientSession: ops]                    [ClientSession: kb]
└──────────────────────────┼───────────────────────────────────────┼───┘
                           │ stdio 管道 (JSON-RPC 2.0)             │ stdio 管道 (JSON-RPC 2.0)
             ┌─────────────▼─────────────┐           ┌─────────────▼─────────────┐
             │ 子进程 1: mcp_server.py   │           │ 子进程 2: kb_mcp_server.py│
             │ (工作区文件 / 微服务监控) │           │ (运维SOP手册 / 上线记录)  │
             └───────────────────────────┘           └───────────────────────────┘
```

### 2.2 `stdio` 传输机制与通信铁律
* **通俗理解**：`stdio`（Standard Input / Output）是同一台机器上两个进程之间“门缝底下递纸条”的本地管道通信。Host 把 MCP Server 当作后台子进程启动，直接接管子进程的 `stdin` 和 `stdout`：Host 往 `stdin` 写入 JSON-RPC 2.0 请求行，Server 计算后将 JSON-RPC 响应写入 `stdout`，Host 实时读取。
* **核心优势**：零网络端口配置、无需 HTTP 鉴权、不受本地防火墙干扰。
* **工程铁律**：在 `stdio` 模式下，MCP Server 代码中**严禁使用 `print()`**！任何非 JSON 文本混入 `stdout` 都会破坏 JSON-RPC 帧结构并触发客户端 `JSONDecodeError`。所有调试日志必须通过 `logging` 定向到 **`sys.stderr`**。

### 2.3 三大核心原语（Primitives）对比

| 原语类型 | 协议方法 | 控制权归属（谁触发调用） | REST 类比 | 典型用途 |
| :--- | :--- | :--- | :--- | :--- |
| **Tools（工具）** | `tools/list`<br>`tools/call` | **Model-controlled（大模型自主决定）** | `POST / PUT` | 有执行动作或检索逻辑的函数，如列目录、读文件、查微服务健康状态。 |
| **Resources（资源）** | `resources/list`<br>`resources/read` | **Application-controlled（宿主程序决定）** | `GET` | 通过 URI（如 `system://server-manifest`）标识的只读数据，由宿主显式拉取并注入上下文。 |
| **Prompts（提示词模板）** | `prompts/list`<br>`prompts/get` | **User-controlled（用户显式触发）** | 模板预设 | 服务端预置的标准工作流模板（类似斜杠命令），辅助用户快速发起复杂任务。 |

---

## 三、10.2 & 10.3 核心实现与桥接机制解析

### 3.1 服务端：类型注解自动编译 Schema（`week10/mcp_server.py`）
1. **SDK 2.x 现代类**：使用 `from mcp.server.mcpserver import MCPServer` 实例化服务端。
2. **零手写 Schema**：通过 `@mcp.tool()` 装饰器与 Python Type Hints（如 `sub_dir: str = "."`）、Docstring，服务端在启动时自动反射生成符合 JSON Schema 规范的 `input_schema`。
3. **路径穿越安全防护**：`_resolve_safe_path()` 使用 `Path.resolve()` 校验解析后的绝对路径是否严格位于 `WORKSPACE_ROOT` 目录内，阻断 `../../` 越权访问。

### 3.2 客户端适配器：`MCPClientBridge`（`week10/mcp_client_agent.py`）
1. **`AsyncExitStack` 生命周期托管**：统一管理 `stdio_client` 子进程管道与 `ClientSession` 异步上下文的创建与退出释放，防止僵尸子进程残留。
2. **闭包工厂防变量覆盖陷阱**：在遍历 `tools_response.tools` 动态注册异步包装器时，通过 `_make_remote_caller(bound_name)` 将当前工具名绑定到独立作用域，避免循环变量延迟绑定导致所有工具指向最后一个工具名。
3. **安全护栏全量继承**：`AsyncReActAgent` 完整保留第 9 周的三道安全护栏（`max_steps` 轮次熔断、`asyncio.wait_for` 单步超时中断、`repeat_threshold=3` 规范化签名防死循环）。

---

## 四、10.4 多 Server 协同架构与实战 Trace 实录

### 4.1 `MultiServerMCPHost` 三大工程机制
* **命名空间前缀隔离**：注册工具时统一重写为 `{server_alias}__{raw_name}`（如 `ops__check_microservice_health` 与 `kb__search_incident_runbook`），彻底杜绝多服务同名工具冲突。
* **单点故障隔离**：在远程调用闭包外层包裹 `try...except`，单台 Server 子进程异常或管道断开时，统一转化为 `"Error: MCP 服务 [alias] 通信中断..."` 文本回填给模型，触发模型自主降级切换排查路径。
* **跨进程并发调用**：模型单轮生成的多个 `tool_calls` 会按命名空间分别路由至对应子进程管道并发执行。

### 4.2 跨服务三跳排障实战 Trace（4 轮收敛）
测试指令：*“线上 `rag-engine` 出现严重延迟，请查出真正根因、检索应急手册（SOP），并核查最近 24 小时上线变更与责任人。”*

1. **Step 1（定位表象与依赖线索）**：并行调用 `ops__check_microservice_health("rag-engine")` 与 `ops__list_workspace_files(".")` $\rightarrow$ 发现 `rag-engine` 状态 `DEGRADED`（CPU 89%），告警指向依赖服务 `billing-api` 配额校验延迟。
2. **Step 2（顺藤摸瓜锁定根因服务）**：调用 `ops__check_microservice_health("billing-api")` $\rightarrow$ 发现 `billing-api` 状态 `CRITICAL`（CPU 96%），告警为 `Redis 连接池耗尽（MaxClients=500）`。
3. **Step 3（跨进程检索 SOP 与变更溯源）**：并行向 `kb` 子进程发起 `kb__search_incident_runbook("Redis 连接池耗尽")` 与 `kb__query_recent_deployments("billing-api")` $\rightarrow$ 命中 `SOP-2026-041`（临时扩容连接池至 1000 并重启僵死 Worker），同时锁定 `09:45` 上线的 `v2.14.3` 阶梯计费异步模块（未配置 Redis 连接回收超时），发布责任人**张工（@zhang-backend）**。
4. **Step 4（输出结构化复盘报告）**：停止工具调用，生成包含级联传导链、SOP 止血动作与责任人跟进清单的完整排障报告。

---

## 五、附录：`mcp 2.x` 踩坑记录与仓库结构

### 附录 A：`mcp 2.3.0` 升级排错全记录
1. **`FastMCP` 更名**：`mcp 2.x` 移除了 `mcp.server.fastmcp`，统一改为 `from mcp.server.mcpserver import MCPServer`。
2. **属性命名改为下划线风格**：`Tool` 与 `CallToolResult` 对象字段由 `inputSchema` / `isError` 改为 `input_schema` / `is_error`，客户端适配时使用 `getattr` 做双版本兼容。
3. **`stdio` 管道防污染**：严禁在 Server 中使用 `print()`，必须使用 `logging.basicConfig(..., stream=sys.stderr)`。

### 附录 B：仓库文件清单与提交命令
```text
ai-agent-learning/
├── requirements.txt                  # 追加 mcp>=2.3.0
├── week10-mcp.md                     # 第 10 周 GitHub 技术总结
└── week10/
    ├── mcp_server.py                 # [10.2] WorkspaceOpsServer 服务端
    ├── mcp_client_agent.py           # [10.3] MCPClientBridge + 异步 ReAct 引擎
    ├── kb_mcp_server.py              # [10.4] OpsKnowledgeBaseServer 知识库服务端
    └── multi_server_demo.py          # [10.4] MultiServerMCPHost 多服务协同实战
```