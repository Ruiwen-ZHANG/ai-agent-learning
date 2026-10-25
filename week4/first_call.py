from common.cost_tracker import CostTracker
import os                           # 标准库，用来读取环境变量
import httpx
import sys
from dotenv import load_dotenv      # 第三方库，负责把 .env 的内容加载进环境变量

load_dotenv()                       # 执行加载，这一行必须在 getenv 之前
key = os.getenv("DEEPSEEK_API_KEY") # 按名字取值，取不到返回 None

if not key:
    raise ValueError("未找到 DEEPSEEK_API_KEY，请检查项目根目录下的 .env 文件")


headers = {
    "Content-Type": "application/json",
    "Authorization":f"Bearer {key}"
}


url = "https://api.deepseek.com/v1/chat/completions"

payload = {
    "model":"deepseek-flash",
    "messages":[{"role":"system","content":"你是一个回复助手，你要回答五十字以内"},
                {"role":"user","content":"什么是SSE"}],
    "temperature":0.7,
    "max_tokens":200,
    "thinking": {"type": "disabled"}
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
print(response.json())        # 再看完整响应

#print(json.dumps(response.json(), indent=2, ensure_ascii=False))

data = response.json()      # 先把响应体转成 Python 字典

content = data["choices"][0]["message"]["content"]
print(content)

finish_reason = data["choices"][0]["finish_reason"]
print(finish_reason)

usage = data["usage"]    # 先拿到整个 usage 字典

tracker.record("deepseek-flash", usage)
tracker.report()
