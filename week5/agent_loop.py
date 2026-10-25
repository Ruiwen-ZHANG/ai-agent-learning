from common.cost_tracker import CostTracker
import os
from dotenv import load_dotenv
import json
import httpx
import sys

load_dotenv()  # 执行加载，这一行必须在 getenv 之前
key = os.getenv("DEEPSEEK_API_KEY")  # 按名字取值，取不到返回 None

if not key:
    raise ValueError("未找到 DEEPSEEK_API_KEY，请检查项目根目录下的 .env 文件")

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {key}"
}

url = "https://api.deepseek.com/v1/chat/completions"

tracker = CostTracker()  # 括号表示调用，这一步会执行 __init__

def get_weather(location):
    weather_data = {"北京":"12℃","上海":"18℃","广州":"26℃"}
    if location not in weather_data:
        return "未查到该城市的天气,只可以查询以下城市的天气['北京','上海','广州']"
    return weather_data[location]

def calculate(a,b,operation):
    if operation == "add":
        result = a + b
        return result
    elif operation == "subtract":
        result = a - b
        return result
    elif operation == "multiply":
        result = a * b
        return result
    elif operation == "divide":
        if b == 0:
            return "除数不能为0"
        else:
            result = a / b
            return result
    else:
        return "不支持该运算类型"

tools = [
{
    "type": "function",              # 目前只有 function 这一种类型
    "function": {
        "name": "get_weather",       # 函数名，模型会原样返回这个名字
        "description": "当用户询问气温、天气状况、是否下雨、冷热时,查询指定城市的当前天气。用户需要先提供城市名。不要用于天气预报、历史天气，不要用于非天气问题。",
        "parameters": {              # 参数用 JSON Schema 描述
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "城市中文名，不含‘市’字，例如：北京、上海",
                }
            },
            "required": ["location"],    # 哪些参数是必填的
        },
    },
},
{
    "type": "function",              # 目前只有 function 这一种类型
    "function": {
        "name": "calculate",       # 函数名，模型会原样返回这个名字
        "description": "用于两数的各种计算，包括加减乘除",
        "parameters": {              # 参数用 JSON Schema 描述
            "type": "object",
            "properties": {
                "a": {
                    "type": "number",
                    "description": "数据（被减数/被除数）",
                },
                "b": {
                    "type": "number",
                    "description": "数据（减数/除数）",
                },
                "operation": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide"],
                    "description": "只包含加减乘除四种基本算法,subtract 计算 a - b，divide 计算 a / b",
                }
            },
            "required": ["a","b","operation"]    # 哪些参数是必填的
        },
    },
},
]

tool_map = {"get_weather": get_weather, "calculate": calculate}

#print(tool_map["calculate"](**{"a": 18, "b": 0, "operation": "divide"}))

def call_llm(messages):

    payload = {
        "model": "deepseek-flash",
        "messages": messages,
        "temperature": 0,
        "max_tokens": 200,
        "thinking": {"type": "disabled"},
        "tools": tools,
    }

    try:
        response = httpx.post(
            url,  # 第一个参数是地址
            headers=headers,  # 请求头字典
            json=payload,  # 请求体，用 json= 参数
            timeout=30,
        )
    except httpx.TimeoutException as e:
        print("超时了:", e)
        sys.exit(1)
    except httpx.RequestError as e:
        print("网络错误：", e)
        sys.exit(1)

    if response.status_code != 200:
        print(response.status_code)  # 先看状态码
        print(response.text)
        sys.exit(1)

    # print(json.dumps(response.json(), indent=2, ensure_ascii=False))

    data = response.json()  # 先把响应体转成 Python 字典

    usage = data["usage"]  # 先拿到整个 usage 字典

    tracker.record("deepseek-flash", usage)

    return data["choices"][0]["message"]

def run_agent(question):
    messages = [
        {"role": "system", "content": "你是一个助手。涉及数学计算时必须使用 calculate 工具，不要自己心算。"},
        {"role": "user", "content": question},
    ]

    for round_num in range(1, 6): #最大轮次本次设定为5
        message = call_llm(messages)
        messages.append(message)

        if "tool_calls" not in message:
            return message["content"]

        for tool_call in message["tool_calls"]:
            call_id = tool_call["id"]
            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]

            try:
                if name not in tool_map:
                    result = f"错误：不存在名为{name}的工具"
                else:
                    args = json.loads(tool_call["function"]["arguments"])
                    result = tool_map[name](**args)
            except json.JSONDecodeError:
                    result = "错误：参数不是合法的 JSON"
            except TypeError as e:
                result = f"错误：参数不正确（{e}）"
            except Exception as e:
                print(f"[开发者日志] 工具 {name} 发生未预期的异常：{type(e).__name__}: {e}")
                result = f"错误：工具执行失败（{e}）"

            print(f"[第{round_num}轮] {name}({args}) → {result}")

            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": str(result),  # str() 保证是字符串，calculate 可能返回数字
            })
    return "超出最大轮数，任务未完成"

print(run_agent("北京和上海今天天气怎么样"))
print(run_agent("北京和上海温差多少度"))
print(run_agent("你好"))
tracker.report()
