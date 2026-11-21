import concurrent.futures
import json
import os
import time
from dotenv import load_dotenv
from openai import OpenAI
from tools import ToolRegistry, create_default_registry

load_dotenv()

SYSTEM_PROMPT = """你是一个严谨的智能助手，能够通过调用外部工具解决复杂问题。
规则：
1. 每次调用工具前，必须先用简短的一两句话在回复文本中说明你的思考过程（为什么需要调用这个工具、打算查什么），然后再发起工具调用。
2. 每次收到工具返回的 Observation 后，根据结果决定是继续调用下一个工具，还是直接给出最终答案。
3. 如果某次工具调用失败或返回提示需要重试，在尝试修正无效后应及时停止或换用其他方法，不要无休止地用相同参数死磕。"""


class ReActAgent:
    def __init__(
        self,
        registry: ToolRegistry,
        model: str | None = None,
        max_steps: int | None = None,
        tool_timeout: float = 30.0,
        max_obs_chars: int = 2000,
        max_history_msgs: int = 12,
    ) -> None:
        self.registry = registry
        self.model = model or os.getenv("MODEL_NAME") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.max_steps = max_steps or int(os.getenv("MAX_TURNS", "10"))
        self.tool_timeout = tool_timeout
        self.max_obs_chars = max_obs_chars
        self.max_history_msgs = max_history_msgs
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    def _execute_with_timeout(self, func_name: str, args: dict) -> str:
        """护栏 3：单工具超时控制（默认 30s），超时后返回错误字符串作为 Observation"""
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.registry.safe_call, func_name, args)
        try:
            return future.result(timeout=self.tool_timeout)
        except concurrent.futures.TimeoutError:
            return f"错误：工具 '{func_name}' 执行超时（超过 {self.tool_timeout} 秒），已强制中断。"
        finally:
            # 不阻塞等待卡死的后台线程
            executor.shutdown(wait=False, cancel_futures=True)

    def _truncate_observation(self, text: str) -> str:
        """上下文管理 A：单条超长 Observation 截断，防止撑爆上下文窗口"""
        if len(text) <= self.max_obs_chars:
            return text
        half = self.max_obs_chars // 2
        omitted = len(text) - self.max_obs_chars
        return f"{text[:half]}\n\n...[中间省略 {omitted} 个字符]...\n\n{text[-half:]}"

    def _trim_messages(self, messages: list[dict]) -> list[dict]:
        """上下文管理 B：安全滑动窗口，保留 system + 初始 user + 最近若干轮完整交互"""
        if len(messages) <= self.max_history_msgs + 2:
            return messages
        head = messages[:2]  # [system, 初始 user]
        tail = messages[-self.max_history_msgs :]
        # 关键防坑：确保裁剪起点不是孤立的 tool 消息，避免破坏 assistant(tool_calls)->tool 配对
        while tail and tail[0].get("role") == "tool":
            tail.pop(0)
        return head + tail

    def _force_final_answer(self, messages: list[dict], reason: str) -> str:
        """熔断兜底：移除 tools 参数，强制模型基于已有信息总结回复"""
        print(f"\n[护栏触发] {reason} -> 正在生成兜底总结...")
        fallback_messages = self._trim_messages(messages) + [
            {
                "role": "user",
                "content": f"系统提示：{reason}。请停止调用任何工具，直接根据目前已收集到的信息向用户总结当前进展和结果。",
            }
        ]
        response = self.client.chat.completions.create(
            model=self.model,
            messages=fallback_messages,
            temperature=0.2,
        )
        answer = response.choices[0].message.content or "任务因触发安全护栏而提前终止。"
        print(f"\n[兜底 Final Answer]\n{answer}")
        return answer

    def run(self, user_query: str) -> str:
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ]
        tools_schema = self.registry.to_schema()
        action_history: list[tuple[str, str]] = []  # 记录 (工具名, 规范化参数JSON)

        print(f"\n{'=' * 60}\n[任务开始] {user_query}\n{'=' * 60}")

        # 护栏 1：最大轮次限制（默认 10 轮）
        for step in range(1, self.max_steps + 1):
            trimmed_messages = self._trim_messages(messages)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=trimmed_messages,
                tools=tools_schema,
                temperature=0.2,
            )
            msg = response.choices[0].message
            thought = (msg.content or "").strip()

            # 无工具调用 -> 正常结束，输出 Final Answer
            if not msg.tool_calls:
                print(f"\n[Step {step}] Final Answer:\n{msg.content}")
                return msg.content or ""

            if thought:
                print(f"\n[Step {step}] Thought:\n{thought}")

            messages.append(msg.model_dump(exclude_none=True))

            for tc in msg.tool_calls:
                func_name = tc.function.name
                raw_args = tc.function.arguments

                try:
                    parsed_args = json.loads(raw_args) if raw_args else {}
                    normalized_args = json.dumps(parsed_args, sort_keys=True, ensure_ascii=False)
                except json.JSONDecodeError as e:
                    parsed_args = None
                    normalized_args = raw_args or ""
                    observation = f"错误：参数不是合法的 JSON 格式 ({e})，请修正后重试。"

                # 护栏 2：连续 3 次调用同一工具且参数完全一致 -> 立即熔断
                signature = (func_name, normalized_args)
                action_history.append(signature)
                if len(action_history) >= 3 and action_history[-1] == action_history[-2] == action_history[-3]:
                    print(f"[Step {step}] Action -> {func_name}({normalized_args}) [重复第 3 次，拦截!]")
                    return self._force_final_answer(
                        messages[:-1],  # 去掉刚追加但未配对 tool 的 assistant 消息
                        f"检测到连续 3 次调用相同工具 '{func_name}' 且参数完全一致，已拦截死循环",
                    )

                print(f"[Step {step}] Action -> {func_name}({normalized_args})")

                if parsed_args is not None:
                    raw_obs = self._execute_with_timeout(func_name, parsed_args)
                    observation = self._truncate_observation(raw_obs)

                print(f"[Step {step}] Observation <- {observation}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": observation,
                    }
                )

        # 跑满 max_steps 仍未结束 -> 触发最大轮次熔断
        return self._force_final_answer(messages, f"已达到最大执行轮次上限 ({self.max_steps} 轮)")


if __name__ == "__main__":
    registry = create_default_registry()

    # 注册两个专用测试工具，用于亲眼验证死循环护栏与超时护栏
    def stubborn_server(ticket_id: str) -> str:
        return f"工单 {ticket_id} 当前状态：排队中（Busy），请立即使用完全相同的参数再次调用本工具查询！"

    def slow_query(seconds: int = 35) -> str:
        time.sleep(seconds)
        return "查询完成"

    registry.register(
        name="check_ticket",
        func=stubborn_server,
        description="查询工单处理状态",
        params={
            "type": "object",
            "properties": {"ticket_id": {"type": "string", "description": "工单编号"}},
            "required": ["ticket_id"],
        },
    )
    registry.register(
        name="slow_query",
        func=slow_query,
        description="执行耗时极长的深度查询",
        params={
            "type": "object",
            "properties": {"seconds": {"type": "integer", "description": "模拟耗时秒数"}},
            "required": [],
        },
    )

    # 为了测试更快，这里把超时设为 3 秒演示超时熔断（默认是 30 秒）
    agent = ReActAgent(registry=registry, max_steps=10, tool_timeout=30.0) #测试完后提交到github上改回了30s

    # 实验 1：故意诱发死循环（观察连续第 3 次重复调用时护栏如何拦截并兜底总结）
    agent.run("帮我查一下工单 T-9527 的最终结果，如果显示排队中就一直用原参数重试直到成功。")

    # 实验 2：故意触发工具超时（观察超时后模型如何收到 Observation 并做出应对）
    agent.run("调用 slow_query 帮我做一次耗时 5 秒的深度查询，如果超时了就告诉我去喝杯咖啡再试。")