import asyncio
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Dict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 复用 10.3 实现的注册中心与异步 ReAct 引擎
from mcp_client_agent import AsyncReActAgent, AsyncToolRegistry


class MultiServerMCPHost:
    """
    支持同时挂载多个 MCP Server 的企业级宿主管理器：
    1. 命名空间前缀隔离（server_alias__tool_name），彻底杜绝重名工具冲突；
    2. 单 Server 异常隔离，某个子进程断开或报错不会导致主进程崩溃；
    3. AsyncExitStack 统一托管所有子进程生命周期。
    """

    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.sessions: Dict[str, ClientSession] = {}

    async def mount_stdio_server(
        self,
        server_alias: str,
        script_path: str,
        registry: AsyncToolRegistry,
    ):
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[script_path],
            env=os.environ.copy(),
        )
        read_stream, write_stream = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        self.sessions[server_alias] = session
        print(f"[Multi-Host] 已挂载 MCP Server [{server_alias}] -> {Path(script_path).name}")

        tools_resp = await session.list_tools()
        for mcp_tool in tools_resp.tools:
            raw_name = mcp_tool.name
            # 命名空间隔离：加上 server_alias__ 前缀
            namespaced_name = f"{server_alias}__{raw_name}"
            tool_desc = f"[{server_alias}服务] {mcp_tool.description or raw_name}"
            tool_schema = (
                getattr(mcp_tool, "input_schema", None)
                or getattr(mcp_tool, "inputSchema", None)
                or {"type": "object", "properties": {}}
            )

            def _make_isolated_caller(alias: str, target_tool: str):
                async def _isolated_call(**kwargs) -> str:
                    try:
                        active_session = self.sessions[alias]
                        result = await active_session.call_tool(target_tool, arguments=kwargs)
                        text_parts = [
                            b.text for b in result.content if hasattr(b, "text")
                        ]
                        output = "\n".join(text_parts) if text_parts else str(result.content)
                        is_err = getattr(result, "is_error", False) or getattr(result, "isError", False)
                        if is_err:
                            return f"Error: [{alias}] 工具执行异常 -> {output}"
                        return output
                    except Exception as e:
                        # 异常隔离：捕获单点子进程崩溃或管道中断，转化为 Error 文本供模型降级处理
                        return (
                            f"Error: MCP 服务 [{alias}] 通信中断或执行异常 "
                            f"({type(e).__name__}: {str(e)})，请尝试其他排查工具。"
                        )

                return _isolated_call

            registry.register(
                name=namespaced_name,
                func=_make_isolated_caller(server_alias, raw_name),
                description=tool_desc,
                parameters=tool_schema,
            )
            print(f"  ├─ 注册命名空间工具: {namespaced_name}")

    async def close_all(self):
        await self.exit_stack.aclose()


async def main():
    base_dir = Path(__file__).resolve().parent
    ops_server = str(base_dir / "mcp_server.py")
    kb_server = str(base_dir / "kb_mcp_server.py")

    registry = AsyncToolRegistry()
    host = MultiServerMCPHost()

    try:
        # 同时挂载两个独立的 MCP Server 子进程
        await host.mount_stdio_server("ops", ops_server, registry)
        await host.mount_stdio_server("kb", kb_server, registry)

        agent = AsyncReActAgent(registry=registry, max_steps=8)

        print("\n" + "=" * 70)
        print("【10.4 综合实战】多 MCP Server 跨服务协同排障与变更溯源")
        print("=" * 70)
        await agent.run(
            "当前线上 rag-engine 出现严重延迟，请帮我完成以下三件事：\n"
            "1. 顺藤摸瓜查出真正的故障服务与具体报错原因；\n"
            "2. 检索内部运维应急手册（SOP），给出对应的应急处置步骤；\n"
            "3. 核查该故障服务最近 24 小时是否有上线变更，定位变更版本和责任人。"
        )
    finally:
        await host.close_all()


if __name__ == "__main__":
    asyncio.run(main())