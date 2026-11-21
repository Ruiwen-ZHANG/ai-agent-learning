import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from tools import ToolRegistry, create_default_registry

load_dotenv()

SYSTEM_PROMPT = """你是一个严谨的智能助手，能够通过调用外部工具解决复杂问题。
规则：
1. 每次调用工具前，必须先用简短的一两句话在回复文本中说明你的思考过程（为什么需要调用这个工具、打算查什么），然后再发起工具调用。
2. 每次收到工具返回的 Observation 后，根据结果决定是继续调用下一个工具，还是直接给出最终答案。
3. 严禁凭空编造数据，所有时间、计算和文件内容必须以工具返回结果为准。"""


class ReActAgent:
    def __init__(self, registry: ToolRegistry, model: str | None = None) -> None:
        self.registry = registry
        self.model = model or os.getenv("MODEL_NAME") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    def run(self, user_query: str) -> str:
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ]
        tools_schema = self.registry.to_schema()

        print(f"\n{'=' * 60}\n[任务开始] {user_query}\n{'=' * 60}")
        step = 0

        while True:
            step += 1
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools_schema,
                temperature=0.2,
            )
            msg = response.choices[0].message

            # 1. 打印模型的 Thought（如果模型输出了文本思考）
            thought = (msg.content or "").strip()
            if thought:
                print(f"\n[Step {step}] Thought:\n{thought}")

            # 2. 判断出口：没有工具调用，说明已得出 Final Answer
            if not msg.tool_calls:
                print(f"\n[Step {step}] Final Answer:\n{msg.content}")
                return msg.content or ""

            # 3. 必须将包含 tool_calls 的 assistant 消息原样存入历史
            messages.append(msg.model_dump(exclude_none=True))

            # 4. 遍历执行所有 tool_calls（兼容并行调用）并回填 Observation
            for tc in msg.tool_calls:
                func_name = tc.function.name
                raw_args = tc.function.arguments
                print(f"[Step {step}] Action -> {func_name}({raw_args})")

                try:
                    parsed_args = json.loads(raw_args) if raw_args else {}
                    observation = self.registry.safe_call(func_name, parsed_args)
                except json.JSONDecodeError as e:
                    observation = f"错误：参数不是合法的 JSON 格式 ({e})，请修正后重试。"

                print(f"[Step {step}] Observation <- {observation}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": observation,
                    }
                )


if __name__ == "__main__":
    registry = create_default_registry()
    agent = ReActAgent(registry=registry)

    # 测试 1：单工具查询
    agent.run("帮我查一下 ReAct 和 MCP 分别是什么？")

    # 测试 2：多工具串联（查时间 -> 数学计算 -> 写文件）
    agent.run(
        "先获取当前日期，计算从今天到 2026 年 12 月 21 日还剩多少天，"
        "然后把结果写入 countdown.txt 文件中，最后告诉我完成情况。"
    )

    # 测试 3：验证自我纠错（故意让它读一个不存在的文件，看它如何应对）
    agent.run("读取 not_exist.txt 的内容；如果文件不存在，就新建这个文件并写入 '初始化完成'。")