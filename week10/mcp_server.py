import logging
import os
import sys
from pathlib import Path
from typing import Dict
from mcp.server.mcpserver import MCPServer

# ==============================================================================
# 关键工程规范：stdio 模式下严禁使用 print() 向 stdout 输出日志！
# 必须将所有日志定向到 sys.stderr，防止污染 JSON-RPC 2.0 通信管道。
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="[MCP-Server] %(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("workspace-mcp-server")

# 初始化 MCPServer 实例（mcp 2.x 官方标准类名）
mcp = MCPServer("WorkspaceOpsServer")

# 锁定工作区根目录（week10 的上一级目录，即 ai-agent-learning 仓库根目录）
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def _resolve_safe_path(relative_path: str) -> Path:
    """安全路径解析：防止路径穿越攻击（如 ../../Windows/System32）"""
    target = (WORKSPACE_ROOT / relative_path).resolve()
    if not str(target).startswith(str(WORKSPACE_ROOT)):
        raise ValueError(f"安全拦截：禁止访问工作区以外的路径 '{relative_path}'")
    return target


# ==============================================================================
# 1. MCP Resource（只读资源原语：由宿主程序或用户显式拉取）
# ==============================================================================
@mcp.resource("system://server-manifest")
def get_server_manifest() -> str:
    """返回当前 MCP Server 的能力清单与工作区根路径信息"""
    return (
        f"Server Name: WorkspaceOpsServer\n"
        f"Protocol: Model Context Protocol (stdio / JSON-RPC 2.0)\n"
        f"Workspace Root: {WORKSPACE_ROOT}\n"
        f"Available Tools: list_workspace_files, read_workspace_file, check_microservice_health"
    )


# ==============================================================================
# 2. MCP Tools（工具原语：由大模型在 ReAct 循环中自主决策调用）
# ==============================================================================
@mcp.tool()
def list_workspace_files(sub_dir: str = ".") -> str:
    """
    列出项目工作区指定子目录下的所有文件与文件夹名称。
    当你需要了解项目里有哪些代码文件、学习笔记或配置文件时，请调用此工具。

    Args:
        sub_dir: 相对于项目根目录的子目录路径，默认为 "."（根目录），例如 "week9" 或 "week10"
    """
    logger.info(f"收到工具调用 list_workspace_files(sub_dir='{sub_dir}')")
    try:
        target_dir = _resolve_safe_path(sub_dir)
        if not target_dir.exists():
            return f"Error: 目录 '{sub_dir}' 不存在。"
        if not target_dir.is_dir():
            return f"Error: '{sub_dir}' 不是一个有效的目录。"

        entries = []
        for item in sorted(target_dir.iterdir()):
            if item.name.startswith(".") or item.name == "__pycache__":
                continue
            tag = "[DIR] " if item.is_dir() else "[FILE]"
            entries.append(f"{tag} {item.name}")

        if not entries:
            return f"目录 '{sub_dir}' 为空。"
        return f"目录 '{sub_dir}' 下的内容如下：\n" + "\n".join(entries)
    except Exception as e:
        return f"Error: 列出目录失败 ({type(e).__name__}: {str(e)})"


@mcp.tool()
def read_workspace_file(relative_path: str) -> str:
    """
    读取项目工作区内指定文本或代码文件的完整内容。
    注意：调用前如果不确定准确文件名，建议先调用 list_workspace_files 查看目录。

    Args:
        relative_path: 相对于项目根目录的文件路径，例如 "requirements.txt" 或 "week9/tools.py"
    """
    logger.info(f"收到工具调用 read_workspace_file(relative_path='{relative_path}')")
    try:
        target_file = _resolve_safe_path(relative_path)
        if not target_file.exists():
            return f"Error: 文件 '{relative_path}' 不存在，请先调用 list_workspace_files 确认文件名。"
        if not target_file.is_file():
            return f"Error: '{relative_path}' 是目录而非文件，无法读取内容。"

        content = target_file.read_text(encoding="utf-8")
        max_chars = 6000
        if len(content) > max_chars:
            return (
                f"文件 '{relative_path}' 内容较长，已截取前 {max_chars} 个字符：\n\n"
                + content[:max_chars]
                + "\n\n... [内容已截断]"
            )
        return f"文件 '{relative_path}' 的内容如下：\n\n{content}"
    except UnicodeDecodeError:
        return f"Error: 文件 '{relative_path}' 不是 UTF-8 文本文件（可能是二进制文件），无法直接读取。"
    except Exception as e:
        return f"Error: 读取文件失败 ({type(e).__name__}: {str(e)})"


@mcp.tool()
def check_microservice_health(service_name: str) -> str:
    """
    查询公司内部微服务的实时运行状态、CPU/内存负载及最近一条告警日志。
    支持查询的服务名称包括：'auth-service'、'rag-engine'、'billing-api'。

    Args:
        service_name: 微服务名称，例如 "rag-engine"
    """
    logger.info(f"收到工具调用 check_microservice_health(service_name='{service_name}')")
    mock_metrics: Dict[str, str] = {
        "auth-service": "状态: HEALTHY | CPU: 24% | 内存: 512MB/2GB | 最近告警: 无",
        "rag-engine": (
            "状态: DEGRADED（性能降级）| CPU: 89% | 内存: 3.8GB/4GB | "
            "最近告警: [2026-11-28 10:12:05] 向量检索线程池队列积压，建议检查依赖服务 billing-api 的配额校验延迟。"
        ),
        "billing-api": (
            "状态: CRITICAL（连接超时）| CPU: 96% | 内存: 1.9GB/2GB | "
            "最近告警: [2026-11-28 10:11:48] Redis 连接池耗尽（MaxClients=500），导致上游调用超时。"
        ),
    }
    key = service_name.strip().lower()
    if key not in mock_metrics:
        return (
            f"Error: 未找到名为 '{service_name}' 的微服务。"
            f"当前可监控的服务列表：{list(mock_metrics.keys())}"
        )
    return f"微服务 [{key}] 监控快照：\n{mock_metrics[key]}"


if __name__ == "__main__":
    logger.info("正在启动 WorkspaceOpsServer (stdio 模式)...")
    mcp.run(transport="stdio")