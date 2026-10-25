from common.cost_tracker import CostTracker
import os
from dotenv import load_dotenv
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

test_cases = [
        ("北京今天多少度", True),
        ("上海现在天气怎么样", True),
        ("深圳热不热", True),
        ("广州现在下雨吗", True),
        ("杭州要穿外套吗", True),
        ("北京有哪些好玩的景点", False),
        ("上海到北京有多远", False),
        ("成都的历史沿革", False),
        ("你好", False),
        ("推荐几本科幻小说", False),
    ]

tracker = CostTracker()  # 括号表示调用，这一步会执行 __init__

def should_call_tool(question, tools):
    messages = [
        {"role": "system", "content": "你是一个助手"},
        {"role": "user", "content": question},
    ]

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

    #print(json.dumps(response.json(), indent=2, ensure_ascii=False))

    data = response.json()  # 先把响应体转成 Python 字典

    usage = data["usage"]  # 先拿到整个 usage 字典

    tracker.record("deepseek-flash", usage)

    message = data["choices"][0]["message"]
    if "tool_calls" in message:
        return True
    else:
        return False

tools_detailed = [
    {
    "type": "function",              # 目前只有 function 这一种类型
    "function": {
        "name": "tool_a",       # 函数名，模型会原样返回这个名字
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
]

tools_vague = [
    {
        "type": "function",
        "function": {
            "name": "tool_a",
            "description":"查询数据",
"parameters": {              # 参数用 JSON Schema 描述
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "输入",
                }
            },
            "required": ["location"],    # 哪些参数是必填的
        },
    }
},
]

tool_sets = [("详细版",tools_detailed),("模糊版",tools_vague)]

for sets in tool_sets:
    true_number = 0
    print("标题:", sets[0])

    for test in test_cases:
        real = should_call_tool(test[0], sets[1])
        if real == test[1]:
            true_number += 1
        print("问题:", test[0],"预期:", test[1],"实际：", real)

    correct_rate = true_number / len(test_cases)
    print("这一套的准确率：:", correct_rate)

tracker.report()