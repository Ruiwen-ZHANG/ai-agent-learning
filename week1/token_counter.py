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
        logging.FileHandler(DATA_DIR / "agent.log", encoding="utf-8", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

class TokenCounter:
    def __init__(self) -> None:
            self.records = []
        # 一个空列表，用来装所有记录

    def record(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
            if prompt_tokens < 0:
                raise ValueError (f"prompt_tokens不能为负数：{prompt_tokens}")
            if completion_tokens < 0:
                raise ValueError (f"completion_tokens不能为负数:{completion_tokens}")
            self.records.append({"model":model,"prompt_tokens":prompt_tokens,
                                 "completion_tokens":completion_tokens})
            logger.info(f"使用模型:{model},发送token消耗：{prompt_tokens},"
                        f"回答token消耗{completion_tokens}")

        # 1. 校验两个 token 数不能为负，违规 raise ValueError（分开校验）
        # 2. 校验通过后，造一个字典 append 进列表
        # 3. 记一条 logger.info

    def __len__(self) -> int:
            return len(self.records)

    # 记录条数

    def total(self) -> int:
        total_count = 0
        for record in self.records:
            total_count = total_count + record["completion_tokens"] + record["prompt_tokens"]
        return total_count

    # 遍历所有记录，把每条的 prompt + completion 累加起来
    # 需要一个变量存累计值，从 0 开始

    def by_model(self) -> dict[str, int]:
        result = {}  # 新建一个空字典存结果

        for record in self.records:
            model = record["model"]
            tokens = record["prompt_tokens"] + record["completion_tokens"]

            # 关键：把 tokens 累加到 result[model] 上
            # 但 model 可能是第一次出现，result 里还没有这个键
            # 用 result.get(model, 0) 拿到"当前值，没有就当 0"
            result[model] = tokens + result.get(model, 0)
        return result

    # 遍历记录，按 model 分组累加
    # 提示：用 result.get(model, 0) 处理"这个模型第一次出现"的情况
    # 返回的必须是新建的字典（你本来就是新建的，天然满足副本要求）

    def top_model(self):
        stats = self.by_model()
        if not stats:  # 空字典是假值
            return None
        return max(stats, key=stats.get)


    def report(self) -> str:
        if not self.records:
            return "暂无记录"

        lines = []
        lines.append("=" * 30)
        lines.append(f"总消耗: {self.total()} tokens")
        lines.append(f"调用次数: {len(self)}")

    # 这里遍历 by_model() 的结果，每个模型加一行

        lines.append(f"消耗最多: {self.top_model()}")
        lines.append("=" * 30)

        return "\n".join(lines)


c = TokenCounter()
c.record("deepseek-chat", 100, 50)
c.record("deepseek-chat", 200, 80)
c.record("gpt-4", 500, 300)

print("总数:", c.total())          # 1230
print("分模型:", c.by_model())     # {'deepseek-chat': 430, 'gpt-4': 800}
print("最贵:", c.top_model())      # gpt-4
print("记录数:", len(c))           # 3
print(c.report())

empty = TokenCounter()
print("空计数器:", empty.top_model())    # None

try:
    c.record("test", -1, 100)
except ValueError as e:
    print("捕获:", e)

# 第 2 周复习：这个类用于统计 Agent 的 token 消耗