import httpx
import os
import sys
from dotenv import load_dotenv      # 第三方库，负责把 .env 的内容加载进环境变量
from common.cost_tracker import CostTracker

load_dotenv()                       # 执行加载，这一行必须在 getenv 之前
key = os.getenv("DEEPSEEK_API_KEY") # 按名字取值，取不到返回 None

if not key:
    raise ValueError("未找到 DEEPSEEK_API_KEY，请检查项目根目录下的 .env 文件")

headers = {
    "Content-Type": "application/json",
    "Authorization":f"Bearer {key}"
}

tracker = CostTracker()

url = "https://api.deepseek.com/v1/chat/completions"
messages = [{"role": "system", "content": "你是一个简洁的助手"}]
while True:
    user_input = input("你: ")
    if user_input == "exit" or user_input == "quit":
        break
    messages.append({"role": "user", "content": user_input})

    payload = {
        "model": "deepseek-flash",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 200,
        "thinking": {"type": "disabled"}
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
    #print(response.json())  # 再看完整响应
    # print(json.dumps(response.json(), indent=2, ensure_ascii=False))

    data = response.json()  # 先把响应体转成 Python 字典
    content = data["choices"][0]["message"]["content"]
    print("AI:",content)

    usage = data["usage"]
    prompt = usage["prompt_tokens"]
    hit = usage["prompt_cache_hit_tokens"]
    miss = usage["prompt_cache_miss_tokens"]
    tracker.record("deepseek-flash", usage)
    print(f"[messages {len(messages)} 条 | 输入 {prompt} | 命中 {hit} | 未命中 {miss}]")

    messages.append({"role": "assistant", "content": content})

tracker.report()
