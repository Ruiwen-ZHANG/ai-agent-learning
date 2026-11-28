import logging
import sys
from typing import Dict
from mcp.server.mcpserver import MCPServer

# 严格遵循 stdio 规范：日志定向至 sys.stderr
logging.basicConfig(
    level=logging.INFO,
    format="[KB-MCP-Server] %(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("kb-mcp-server")

mcp = MCPServer("OpsKnowledgeBaseServer")


@mcp.tool()
def search_incident_runbook(error_keyword: str) -> str:
    """
    根据报错关键词检索内部运维应急手册（SOP）与标准修复方案。
    当监控告警中出现具体异常（如 Redis 连接池耗尽、OOM、队列积压等）时调用此工具。

    Args:
        error_keyword: 故障关键词，例如 "Redis"、"MaxClients" 或 "连接池"
    """
    logger.info(f"收到知识库检索请求: error_keyword='{error_keyword}'")
    runbooks: Dict[str, str] = {
        "redis": (
            "【SOP-2026-041】Redis 连接池耗尽（MaxClients=500）应急处置手册：\n"
            "1. 根因常见于上游批量计费任务未复用连接或连接泄漏；\n"
            "2. 立即执行：调用运维平台将 billing-api 的连接池上限临时扩容至 1000，并重启僵死 Worker；\n"
            "3. 长期治理：检查最近 24 小时内的代码变更记录（可调用 query_recent_deployments 核对责任人）。"
        ),
        "rag": (
            "【SOP-2026-019】RAG 检索队列积压处置手册：\n"
            "通常由下游鉴权或计费配额校验接口（billing-api）超时引起，请优先排查下游依赖服务状态。"
        ),
    }
    kw = error_keyword.strip().lower()
    for key, doc in runbooks.items():
        if key in kw or kw in key:
            return doc
    return f"未找到与 '{error_keyword}' 强匹配的应急手册，可尝试关键词：['redis', 'rag']。"


@mcp.tool()
def query_recent_deployments(service_name: str) -> str:
    """
    查询指定微服务最近 24 小时内的上线发布记录与变更责任人。

    Args:
        service_name: 微服务名称，例如 "billing-api"
    """
    logger.info(f"收到变更记录查询: service_name='{service_name}'")
    deployments: Dict[str, str] = {
        "billing-api": (
            "最近变更记录 [billing-api]：\n"
            "- 时间：2026-11-28 09:45:00\n"
            "- 版本：v2.14.3\n"
            "- 变更内容：上线阶梯计费异步结算模块（未配置 Redis 连接回收超时）\n"
            "- 发布人：张工（@zhang-backend）"
        ),
        "rag-engine": "最近 24 小时无上线发布记录。",
        "auth-service": "最近 24 小时无上线发布记录。",
    }
    return deployments.get(
        service_name.strip().lower(),
        f"未查询到服务 '{service_name}' 的变更记录。",
    )


if __name__ == "__main__":
    logger.info("正在启动 OpsKnowledgeBaseServer (stdio 模式)...")
    mcp.run(transport="stdio")