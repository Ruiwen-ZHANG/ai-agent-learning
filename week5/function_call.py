from week4.cost_tracker import CostTracker
import os
from dotenv import load_dotenv
import json
import httpx
import sys

def get_weather(location):
    weather = f"{location}今天 12℃，晴"
    return weather

load_dotenv()                       # 执行加载，这一行必须在 getenv 之前
key = os.getenv("DEEPSEEK_API_KEY") # 按名字取值，取不到返回 None

if not key:
    raise ValueError("未找到 DEEPSEEK_API_KEY，请检查项目根目录下的 .env 文件")


headers = {
    "Content-Type": "application/json",
    "Authorization":f"Bearer {key}"
}

tools = [
    {
        "type": "function",              # 目前只有 function 这一种类型
        "function": {
            "name": "get_weather",       # 函数名，模型会原样返回这个名字
            "description": "查询指定城市的当前天气。用户需要先提供城市名。",
            "parameters": {              # 参数用 JSON Schema 描述
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市名，例如：北京、上海",
                    }
                },
                "required": ["location"],    # 哪些参数是必填的
            },
        },
    },
]

url = "https://api.deepseek.com/v1/chat/completions"

messages = [
    {"role":"system","content":"你是一个天气查询助手"},
    {"role":"user","content":"北京今天多少度？"},
    ]

payload = {
    "model":"deepseek-flash",
    "messages":messages,
    "temperature":0,
    "max_tokens":200,
    "thinking": {"type": "disabled"},
    "tools": tools,
}

tracker = CostTracker()     # 括号表示调用，这一步会执行 __init__

try:
    response = httpx.post(
         url,           # 第一个参数是地址
         headers=headers,    # 请求头字典
         json=payload,       # 请求体，用 json= 参数
         timeout=30,
    )
except httpx.TimeoutException as e:
    print("超时了:",e)
    sys.exit(1)
except httpx.RequestError as e:
    print("网络错误：",e)
    sys.exit(1)

if response.status_code != 200:
    print(response.status_code)   # 先看状态码
    print(response.text)
    sys.exit(1)

print(json.dumps(response.json(), indent=2, ensure_ascii=False))

data = response.json()      # 先把响应体转成 Python 字典
name = data["choices"][0]["message"]["tool_calls"][0]["function"]["name"]
print(name)

arguments = data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
arguments_json = json.loads(arguments)
location = arguments_json["location"]
print(location)

tool_call_id = data["choices"][0]["message"]["tool_calls"][0]["id"]
print(tool_call_id)

weather = get_weather(location)
print(weather)

usage = data["usage"]    # 先拿到整个 usage 字典

tracker.record("deepseek-flash", usage)

message = data["choices"][0]["message"]
messages.append(message)

messages.append({
    "role": "tool",
    "tool_call_id": tool_call_id,     # 填你解析出来的 id 变量名
    "content": weather,          # 填 get_weather 返回值的变量名
})

print(len(messages))        # 应该是 4
print(json.dumps(messages, indent=2, ensure_ascii=False))

#以下部分为第二次发送

try:
    response2 = httpx.post(
         url,           # 第一个参数是地址
         headers=headers,    # 请求头字典
         json=payload,       # 请求体，用 json= 参数
         timeout=30,
    )
except httpx.TimeoutException as e:
    print("超时了:",e)
    sys.exit(1)
except httpx.RequestError as e:
    print("网络错误：",e)
    sys.exit(1)

if response2.status_code != 200:
    print(response2.status_code)   # 先看状态码
    print(response2.text)
    sys.exit(1)

print(json.dumps(response2.json(), indent=2, ensure_ascii=False))

data2 = response2.json()
content = data2["choices"][0]["message"]["content"]
print(content)

usage2 = data2["usage"]    # 先拿到整个 usage 字典

tracker.record("deepseek-flash", usage2)
tracker.report()