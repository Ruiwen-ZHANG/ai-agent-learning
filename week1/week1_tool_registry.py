# ToolRegistry 工具注册表
#Agent 需要管理一批工具（函数）。模型说"我要调用 get_weather"，你的代码得能根据这个名字找到对应的函数并执行。
import logging
import sys
from typing import Callable
from pathlib import Path

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

# 下面才是异常类、ToolRegistry、测试代码


class ToolError(Exception):
    """工具相关错误的基类"""

class ToolNotFoundError(ToolError):
    """工具不存在"""


class ToolExecutionError(ToolError):
    """工具执行失败"""

class ToolRegistry:
    #创建一个空“柜子”，里面用于存放很多个函数工具
    def __init__(self) -> None:
        self.tools:dict[str,dict] = {}
    #将函数名称和函数本身即其解释作为一个字典（可以理解成一整个工具）放进原本的空“柜子”
    def register(self, name, func, description) -> None:
        if name in self.tools:
            logger.warning("重名警告")
        self.tools[name] = {"func": func, "description": description}


    def get(self,name:str) -> Callable|None:
        if name in self.tools:
          return self.tools[name]["func"]
        return None

    def call(self, name:str,*args):
        if name not in self.tools:
            logger.error(f"工具不存在: {name}，已注册: {self.list_names()}")
            raise ToolNotFoundError(f"工具不存在: {name}，已注册: {self.list_names()}")
        try:
            result = self.tools[name]["func"](*args)
            logger.info(f"调用工具 {name}, 参数={args}, 结果={result}")
            return result
        except Exception as e:
            logger.exception(f"工具 {name}")
            raise ToolExecutionError(
                f"工具 {name} 执行失败: {type(e).__name__}: {e}"
            ) from e



    def list_names(self):
        return list(self.tools.keys())

    def to_schema(self):
        result = []  # 每次调用现造一个新的
        for k, v in self.tools.items():
            result.append({"name": k, "description": v["description"]})
        return result  # 交出去，方法结束，result 这个变量名就没了

    def __len__(self) -> int:
        return len(self.tools.keys())

    # 返回工具数量。想想 self.tools 是字典，怎么数它有几格

    def __contains__(self, name: str) -> bool:
        return name in self.tools

    # 返回 True/False。想想怎么判断一个键在不在字典里
    # 提示：你在 get 和 call 里已经用过这个语法了

#新增safe_call(self, name, *args) -> str
    def safe_call(self, name: str, *args) -> str:
        try:
            result = self.call(name, *args)
            return str(result)
        except ToolNotFoundError as e:
            return f"工具不存在: {e}"
        except ToolExecutionError as e:
            return f"执行出错: {e}"




def add(a, b):
    return a + b

def divide(a, b):
    return a / b

reg = ToolRegistry()
reg.register("add", add, "两数相加")
reg.register("divide", divide, "两数相除")

print(reg.safe_call("add", 3, 5))
print(reg.safe_call("divide", 10, 2))
print(reg.safe_call("divide", 10, 0))
print(reg.safe_call("不存在", 1))

try:
    reg.call("不存在")
except ToolNotFoundError as e:
    print("捕获 ToolNotFoundError:", e)

try:
    reg.call("divide", 1, 0)
except ToolExecutionError as e:
    print("捕获 ToolExecutionError:", e)
    print("原始异常:", type(e.__cause__).__name__)

    log_file = DATA_DIR / "agent.log"

    print("=" * 50)
    print("日志路径:", log_file)
    print("文件存在:", log_file.exists())
    print("文件大小:", log_file.stat().st_size, "字节")
    print("=" * 50)
    print(log_file.read_text(encoding="utf-8"))