from pydantic import BaseModel, Field, ValidationError
from typing import Literal


class TokenRecord(BaseModel):
    model: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)

class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    model: str = "deepseek-chat"
    messages: list[Message]
    temperature: float = Field(0.7, ge=0, le=2)

if __name__ == "__main__":
    test = [
    ("正常整数", {"model": "x", "prompt_tokens": 10, "completion_tokens": 50}),
    ("字符串数字", {"model": "y", "prompt_tokens": "100", "completion_tokens": 50}),
    ("非法字符串", {"model": "z", "prompt_tokens": "abc", "completion_tokens": 50}),
    ("负数", {"model": "a", "prompt_tokens": -1, "completion_tokens": 50}),
]
# 列表里每个元素是一个【元组】，装两样东西：
#   ("说明文字", {原始数据字典})
#
# 注意里面【没有 TokenRecord(...)】—— 只是普通的字典。
# 创建对象的动作留到 try 里面，这样失败了才能被捕获。

    for info, data in test:
    # 元组解包：把 ("正常整数", {...}) 拆成 info 和 data 两个变量
        print(f"--- {info} ---")
        try:
           r = TokenRecord(**data)
           print("成功:", r)
           print("   prompt_tokens 类型:", type(r.prompt_tokens).__name__)
        except ValidationError as e:
           print("校验失败:")
           print(e)
        print()

nested_tests = [
    ("合法数据", {
        "messages": [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好"},
        ]
    }),
    ("错误的 role", {
        "messages": [
            {"role": "system", "content": "你是助手"},
            {"role": "User", "content": "你好"},      # 大写 U
        ]
    }),
    ("缺 content 字段", {
        "messages": [
            {"role": "user"},                          # 少了 content
        ]
    }),
    ("temperature 超范围", {
        "messages": [{"role": "user", "content": "你好"}],
        "temperature": 3.5,                            # 超过 le=2
    }),
]

for info, data in nested_tests:
    print(f"--- {info} ---")
    try:
        req = ChatRequest(**data)
        print("成功:", req)
        print("   第一条消息的类型:", type(req.messages[0]).__name__)
    except ValidationError as e:
        print("校验失败:")
        print(e)
    print()

    req = ChatRequest(
    messages=[
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"},
    ]
)

print("--- 模型转字典 ---")
d = req.model_dump()
print(d)
print("类型:", type(d).__name__)
print("messages[0] 的类型:", type(d["messages"][0]).__name__)
# 注意：转成字典后，里面的 Message 对象也变回字典了

print("\n--- 模型转 JSON 字符串 ---")
s = req.model_dump_json(indent=2)
print(s)
print("类型:", type(s).__name__)

print("\n--- JSON 字符串转回模型 ---")
req2 = ChatRequest.model_validate_json(s)
print(req2)
print("类型:", type(req2).__name__)
print("两个对象相等吗:", req == req2)

