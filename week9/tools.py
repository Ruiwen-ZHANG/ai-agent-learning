import ast
import json
import logging
import operator
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(DATA_DIR / "agent.log", encoding="utf-8", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ==================== 1. 自定义异常体系 ====================
class ToolError(Exception):
    """工具相关错误的基类"""


class ToolNotFoundError(ToolError):
    """工具不存在"""


class ToolExecutionError(ToolError):
    """工具执行失败"""


class ToolArgumentError(ToolError):
    """参数有问题：比如不是字典、缺参数、参数名不对"""


# ==================== 2. 工具注册表 ====================
class ToolRegistry:
    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}

    def _normalize(self, name: str) -> str:
        return name.strip().lower()

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        description: str,
        params: dict[str, Any],
    ) -> None:
        name = self._normalize(name)
        if name in self.tools:
            logger.warning(f"重名警告: {name}")
        self.tools[name] = {
            "func": func,
            "description": description,
            "params": params,
        }

    def get(self, name: str) -> Callable[..., Any] | None:
        name = self._normalize(name)
        if name in self.tools:
            return self.tools[name]["func"]
        return None

    def call(self, name: str, args: dict[str, Any] | None = None) -> Any:
        name = self._normalize(name)
        args = args or {}

        if name not in self.tools:
            logger.error(f"工具不存在: {name}，已注册: {self.list_names()}")
            raise ToolNotFoundError(f"工具不存在: {name}，已注册: {self.list_names()}")

        if not isinstance(args, dict):
            raise ToolArgumentError(
                f"工具 {name} 的参数必须是 JSON 对象，收到的是 {type(args).__name__}，"
                f"正确格式：{self.tools[name]['params']}"
            )

        try:
            result = self.tools[name]["func"](**args)
            logger.info(f"调用工具 {name}, 参数={args}, 结果={result}")
            return result
        except TypeError as e:
            # 统一使用单引号避免 Python < 3.12 语法报错
            raise ToolArgumentError(
                f"工具 {name} 参数不正确 ({e})，正确格式：{self.tools[name]['params']}"
            ) from e
        except Exception as e:
            logger.exception(f"工具 {name} 执行异常")
            raise ToolExecutionError(
                f"工具 {name} 执行失败: {type(e).__name__}: {e}"
            ) from e

    def safe_call(self, name: str, args: dict[str, Any] | None = None) -> str:
        """安全调用：永远返回字符串、不抛异常，直接作为 Observation 回填给模型"""
        try:
            result = self.call(name, args)
            return str(result)
        except ToolError as e:
            return f"错误：{e}"

    def list_names(self) -> list[str]:
        return list(self.tools.keys())

    def to_schema(self) -> list[dict[str, Any]]:
        """导出标准 OpenAI / DeepSeek Function Calling 格式的 tools 列表"""
        schemas = []
        for name, info in self.tools.items():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": info["description"],
                        "parameters": info["params"],
                    },
                }
            )
        return schemas

    def render_for_prompt(self) -> str:
        """用于纯文本 System Prompt 注入的工具说明"""
        lines = []
        for name, info in self.tools.items():
            lines.append(f"- {name}: {info['description']}")
            lines.append(f"  参数 Schema: {json.dumps(info['params'], ensure_ascii=False)}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.tools)

    def __contains__(self, name: str) -> bool:
        return self._normalize(name) in self.tools


# ==================== 3. 路线要求的 4 个基础工具 ====================
def get_current_time() -> str:
    """获取当前系统日期与时间"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")


def calculate(expression: str) -> str:
    """安全计算数学表达式（支持 + - * / ** % 和括号，比 eval 更安全）"""
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
    }

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](_eval(node.operand))
        raise ValueError(f"不支持的表达式语法: {ast.dump(node)}")

    tree = ast.parse(expression.strip(), mode="eval")
    result = _eval(tree.body)
    return str(round(result, 6) if isinstance(result, float) else result)


def file_ops(action: str, filename: str, content: str = "") -> str:
    """在 data/ 沙箱目录内读写文件，防止路径穿越"""
    target_path = (DATA_DIR / filename).resolve()
    if DATA_DIR not in target_path.parents and target_path != DATA_DIR:
        raise ValueError("安全拦截：只允许访问 data/ 目录下的文件")

    if action == "read":
        if not target_path.exists():
            raise FileNotFoundError(f"文件不存在: {filename}")
        return target_path.read_text(encoding="utf-8")
    elif action == "write":
        target_path.write_text(content, encoding="utf-8")
        return f"成功写入 {len(content)} 个字符到 {filename}"
    else:
        raise ValueError(f"不支持的操作类型: {action}，仅支持 'read' 或 'write'")


def web_search(query: str) -> str:
    """模拟网络搜索工具（无需额外 API Key，方便本地测试 ReAct 循环）"""
    mock_db = {
        "react": "ReAct (Reasoning and Acting) 由 Yao et al. 于 2022 年提出，核心范式是 Thought -> Action -> Observation 循环。",
        "mcp": "MCP (Model Context Protocol) 是标准化大模型与外部工具/数据源连接协议，包含 Tools、Resources、Prompts 三要素。",
        "deepseek": "DeepSeek API 完全兼容 OpenAI Chat Completions 接口规范，支持 Function Calling 与流式输出。",
    }
    q_lower = query.lower()
    hits = [v for k, v in mock_db.items() if k in q_lower]
    if hits:
        return "\n".join(hits)
    return f"未找到与 '{query}' 高度匹配的结果，请尝试更换更简短的英文关键词（如 ReAct、MCP、DeepSeek）。"


def create_default_registry() -> ToolRegistry:
    """工厂函数：创建并注册好默认 4 个工具的注册表，供 react_core 直接导入"""
    reg = ToolRegistry()

    reg.register(
        name="get_current_time",
        func=get_current_time,
        description="获取当前的日期、时间和星期几",
        params={"type": "object", "properties": {}, "required": []},
    )

    reg.register(
        name="calculate",
        func=calculate,
        description="计算数学表达式，如 '24 * 60' 或 '(100 - 25) / 3'",
        params={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "纯数学运算表达式"}
            },
            "required": ["expression"],
        },
    )

    reg.register(
        name="file_ops",
        func=file_ops,
        description="读取或写入本地 data 目录下的文本文件",
        params={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write"],
                    "description": "操作类型：read 读取，write 写入",
                },
                "filename": {"type": "string", "description": "文件名，如 note.txt"},
                "content": {"type": "string", "description": "写入时的文本内容（读取时可不填）"},
            },
            "required": ["action", "filename"],
        },
    )

    reg.register(
        name="web_search",
        func=web_search,
        description="搜索技术概念或百科知识",
        params={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"],
        },
    )
    return reg


# ==================== 4. 单元测试（仅直接运行本文件时触发） ====================
if __name__ == "__main__":
    reg = create_default_registry()
    print(f"已注册 {len(reg)} 个工具: {reg.list_names()}")
    print("1. 时间:", reg.safe_call("get_current_time"))
    print("2. 计算:", reg.safe_call("calculate", {"expression": "(12 + 8) * 3"}))
    print("3. 除零错误:", reg.safe_call("calculate", {"expression": "10 / 0"}))
    print("4. 写文件:", reg.safe_call("file_ops", {"action": "write", "filename": "test.txt", "content": "Hello ReAct!"}))
    print("5. 读文件:", reg.safe_call("file_ops", {"action": "read", "filename": "test.txt"}))
    print("6. 缺参拦截:", reg.safe_call("calculate", {"wrong_key": "1+1"}))
    print("7. 不存在工具:", reg.safe_call("fly_to_moon", {}))