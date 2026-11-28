import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

# 加载根目录 .env 中的 DEEPSEEK_API_KEY
load_dotenv()


# ==============================================================================
# 1. 异步工具注册中心（升级自第 9 周 ToolRegistry，支持同步与异步 MCP 远程工具）
# ==============================================================================
class AsyncToolRegistry:
    """支持本地函数与远程 MCP 工具统一挂载的注册中心"""

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        func: Callable[..., Coroutine[Any, Any, str]],
        description: str,
        parameters: Dict[str, Any],
    ):
        self._tools[name] = {
            "name": name,
            "func": func,
            "description": description,
            "parameters": parameters,
        }

    def to_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in self._tools.values()
        ]

    async def safe_call(self, name: str, arguments: Dict[str, Any]) -> str:
        if name not in self._tools:
            return f"Error: 未找到工具 '{name}'，当前可用工具：{list(self._tools.keys())}"
        try:
            return await self._tools[name]["func"](**arguments)
        except Exception as e:
            return f"Error: 调用工具 '{name}' 失败 ({type(e).__name__}: {str(e)})"

    async def call(self, name: str, raw_arguments: str) -> str:
        try:
            args = json.loads(raw_arguments) if raw_arguments else {}
            if not isinstance(args, dict):
                return f"Error: 参数必须是 JSON 对象，当前类型为 {type(args).__name__}"
        except json.JSONDecodeError as e:
            return f"Error: 参数 JSON 解析失败 ({str(e)})，请输出合法的 JSON 格式。"
        return await self.safe_call(name, args)


# ==============================================================================
# 2. MCP Client 协议桥接器（负责拉起 Server 子进程、协议握手与工具动态转译）
# ==============================================================================
class MCPClientBridge:
    """管理与 MCP Server 的 stdio 会话生命周期，并将远程工具注入 AsyncToolRegistry"""

    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.session: ClientSession | None = None

    async def connect_stdio_server(self, server_script_path: str, registry: AsyncToolRegistry):
        # 使用当前虚拟环境的 python 解释器启动 MCP Server 子进程
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_script_path],
            env=os.environ.copy(),
        )

        # 建立 stdio 读写管道并初始化 ClientSession
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        read_stream, write_stream = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

        # 发送 JSON-RPC initialize 握手
        await self.session.initialize()
        print(f"[MCP-Client] 成功连接服务端: {Path(server_script_path).name}")

        # 动态拉取远程工具列表并转译注册（零手写 JSON Schema！）
        tools_response = await self.session.list_tools()
        for mcp_tool in tools_response.tools:
            tool_name = mcp_tool.name
            tool_desc = mcp_tool.description or f"MCP 远程工具: {tool_name}"
            # mcp 2.x 使用 snake_case 的 input_schema（兼容 1.x 的 inputSchema）
            tool_schema = (
                    getattr(mcp_tool, "input_schema", None)
                    or getattr(mcp_tool, "inputSchema", None)
                    or {"type": "object", "properties": {}}
            )

            # 使用闭包工厂绑定当前 tool_name，避免循环变量覆盖陷阱
            def _make_remote_caller(bound_name: str):
                async def _remote_call(**kwargs) -> str:
                    assert self.session is not None
                    result = await self.session.call_tool(bound_name, arguments=kwargs)
                    text_parts = [
                        block.text for block in result.content if hasattr(block, "text")
                    ]
                    output = "\n".join(text_parts) if text_parts else str(result.content)
                    # mcp 2.x 使用 is_error（兼容 1.x 的 isError）
                    is_err = getattr(result, "is_error", False) or getattr(result, "isError", False)
                    if is_err:
                        return f"Error: MCP 服务端返回执行错误 -> {output}"
                    return output

                return _remote_call

            registry.register(
                name=tool_name,
                func=_make_remote_caller(tool_name),
                description=tool_desc,
                parameters=tool_schema,
            )
            print(f"  ├─ 已动态挂载 MCP 工具: {tool_name}")

        # 顺手演示读取 MCP Resource（Application-controlled 只读资源）
        resources_resp = await self.session.list_resources()
        if resources_resp.resources:
            first_uri = resources_resp.resources[0].uri
            res_content = await self.session.read_resource(first_uri)
            manifest_text = res_content.contents[0].text if res_content.contents else ""
            print(f"  └─ 已读取服务端 Resource [{first_uri}]:\n     {manifest_text.replace(chr(10), chr(10) + '     ')}")

    async def close(self):
        await self.exit_stack.aclose()


# ==============================================================================
# 3. 异步 ReActAgent 主循环（完整保留第 9 周三道安全护栏）
# ==============================================================================
class AsyncReActAgent:
    """接入 MCP 工具生态的 ReAct 智能体核心引擎"""

    def __init__(
        self,
        registry: AsyncToolRegistry,
        model: str = "deepseek-chat",
        max_steps: int = 8,
        tool_timeout: float = 30.0,
        repeat_threshold: int = 3,
    ):
        self.client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        self.registry = registry
        self.model = model
        self.max_steps = max_steps
        self.tool_timeout = tool_timeout
        self.repeat_threshold = repeat_threshold

    def _normalize_action(self, tool_name: str, raw_args: str) -> str:
        try:
            parsed = json.loads(raw_args) if raw_args else {}
            norm_args = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        except Exception:
            norm_args = str(raw_args).strip()
        return f"{tool_name}::{norm_args}"

    async def _execute_with_timeout(self, tool_name: str, raw_args: str) -> str:
        try:
            return await asyncio.wait_for(
                self.registry.call(tool_name, raw_args),
                timeout=self.tool_timeout,
            )
        except asyncio.TimeoutError:
            return (
                f"Error: MCP 工具 '{tool_name}' 执行超时（超过 {self.tool_timeout} 秒已强制中断）。"
                "请尝试其他排查路径或直接汇总现有信息。"
            )

    async def _fallback_summary(self, messages: List[Dict[str, Any]], reason: str) -> str:
        messages.append({
            "role": "user",
            "content": f"[系统安全护栏触发：{reason}] 请停止调用任何工具，直接根据已有信息给出总结。",
        })
        resp = await self.client.chat.completions.create(model=self.model, messages=messages)
        return resp.choices[0].message.content or f"任务因护栏终止：{reason}"

    async def run(self, user_query: str) -> str:
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是一个具备外部工具调用能力的智能运维与研发助手，遵循 ReAct（思考-行动-观察）模式。"
                    "请善用已挂载的 MCP 工具探索工作区文件或排查微服务故障；"
                    "如果线索指向其他文件或依赖服务，请继续追查直至定位根本原因。"
                ),
            },
            {"role": "user", "content": user_query},
        ]
        action_history: List[str] = []

        for step in range(1, self.max_steps + 1):
            print(f"\n--- [Step {step}/{self.max_steps}] ---")
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.registry.to_schema(),
                tool_choice="auto",
            )
            msg = response.choices[0].message

            if msg.content:
                print(f"[Thought]: {msg.content}")

            if not msg.tool_calls:
                print(f"[Final Answer]: {msg.content}")
                return msg.content or ""

            messages.append(msg.model_dump(exclude_none=True))

            for tool_call in msg.tool_calls:
                t_name = tool_call.function.name
                t_args = tool_call.function.arguments
                print(f"[Action]: 通过 MCP 调用 {t_name}({t_args})")

                # 护栏 2：死循环检测
                sig = self._normalize_action(t_name, t_args)
                action_history.append(sig)
                if (
                    len(action_history) >= self.repeat_threshold
                    and len(set(action_history[-self.repeat_threshold:])) == 1
                ):
                    reason = f"连续 {self.repeat_threshold} 次重复相同 MCP 调用 ({sig})"
                    print(f"[Guardrail Triggered]: {reason}")
                    return await self._fallback_summary(messages, reason)

                # 护栏 3：单步超时控制
                observation = await self._execute_with_timeout(t_name, t_args)
                print(f"[Observation]: {observation}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": observation,
                })

        # 护栏 1：最大轮次熔断
        reason = f"已达到最大允许轮次 max_steps={self.max_steps}"
        print(f"[Guardrail Triggered]: {reason}")
        return await self._fallback_summary(messages, reason)


# ==============================================================================
# 4. 端到端联调测试入口
# ==============================================================================
async def main():
    server_path = str(Path(__file__).resolve().parent / "mcp_server.py")
    registry = AsyncToolRegistry()
    bridge = MCPClientBridge()

    try:
        # 1. 连接 MCP Server，自动拉取 Tools 与 Resource
        await bridge.connect_stdio_server(server_path, registry)
        agent = AsyncReActAgent(registry=registry, max_steps=6)

        # 2. 实战测试一：多跳故障溯源（rag-engine 告警线索指向 billing-api）
        print("\n" + "=" * 70)
        print("【实战测试 1】跨服务多跳故障根因定位（MCP 远程工具链式调用）")
        print("=" * 70)
        await agent.run(
            "线上反馈 rag-engine 服务响应很慢，请帮我排查它当前的健康状态，并顺藤摸瓜找出导致慢查询的真正根因。"
        )

        # 3. 实战测试二：自主探索本地工作区文件（先列目录 -> 再读指定代码）
        print("\n" + "=" * 70)
        print("【实战测试 2】自主探索工作区代码结构并分析第 9 周实现")
        print("=" * 70)
        await agent.run(
            "请查看一下我项目里 week9 文件夹下有哪些文件，并读取其中一个核心文件，用三句话总结它的主要功能。"
        )
    finally:
        # 确保安全关闭子进程与 stdio 管道
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())