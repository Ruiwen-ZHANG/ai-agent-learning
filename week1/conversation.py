from typing import Literal

Role = Literal["system", "user", "assistant", "tool"]
# 定义一个类型别名。后面 add 方法的 role 参数就用 Role 做注解。

class Conversation:
    def __init__(self, system_prompt:str, max_turns:int =10) -> None:
        # 初始化 self.messages，第一条放 system 消息
        self.messages = [{"role": "system", "content": system_prompt}]
        # 保存 self.max_turns
        self.max_turns = max_turns

    def add(self, role: Role, content: str) -> None:
        # role 的注解用 Role，也就是那四个字面量之一。
        # 传别的字符串时 PyCharm 会标出来。
        self.messages.append({"role": role, "content": content})
        self._trim()

    def add_user(self, content:str) -> None:
        # 追加 {"role": "user", "content": content}
        self.messages.append({"role": "user", "content": content})
        self._trim()

    def add_assistant(self, content:str) -> None:
        # 同上，role 换成 "assistant"
        self.messages.append({"role": "assistant", "content": content})
        self._trim()

    def _trim(self) -> None:
        # 除 system 外，最多保留 max_turns * 2 条消息
        limit = self.max_turns * 2
        if len(self.messages) - 1 > limit:
            self.messages = [self.messages[0]] + self.messages[-limit:]

    def to_api_format(self) -> list[dict[str,str]]:
        # 返回 self.messages 的【副本】，不是本体
        # 提示：list(self.messages) 或 self.messages[:]
        return list(self.messages)

    def __len__(self) ->int:
        """魔术方法。实现后可以直接对实例用 len()。

        len(conv) 会自动调用这个方法，
        效果等同于 len(conv.messages)，但写起来更自然。
        """
        return len(self.messages)

conv = Conversation("你是助手", max_turns=2)

for i in range(5):
    conv.add_user(f"问题{i}")
    conv.add_assistant(f"回答{i}")

print("总条数:", len(conv))          # __len__ 生效，直接对实例用 len()
for m in conv.to_api_format():
    print(m["role"], "|", m["content"])

print("-" * 30)

# 验证浅拷贝确实隔离了列表层面的修改
msgs = conv.to_api_format()
print("是同一个对象吗?", msgs is conv.messages)
msgs.clear()
print("清空副本后，内部还剩:", len(conv))

conv.add("User", "你好")        # 大写 U → PyCharm 应该标红
conv.add_user(123)              # 传整数 → PyCharm 应该标黄