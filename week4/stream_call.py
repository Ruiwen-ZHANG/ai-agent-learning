from cost_tracker import CostTracker
import os                           # 标准库，用来读取环境变量
import httpx
import json
import sys
import time
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

start = time.perf_counter()

payload = {
    "model":"deepseek-flash",
    "messages":[{"role":"system","content":"你是一个回复助手，你要回答五十字以内"},
                {"role":"user","content":"什么是SSE"}],
    "temperature":0.7,
    "max_tokens":200,
    "thinking": {"type": "disabled"},
    "stream":True,
"stream_options": {"include_usage": True}
}

tracker = CostTracker()     # 括号表示调用，这一步会执行 __init__
full_reply = ""      # 先创建这个变量，初始内容为空字符串

ttft = None

with httpx.stream(
    "POST",
    url,
    headers=headers,
    json=payload,
    timeout=60,
) as response:
   for line in response.iter_lines():
       if not line:
           continue  # continue 表示跳过本轮循环，直接进入下一轮
       payload_str = line.replace("data: ", "")  # 把这段文字换成空
       if payload_str == "[DONE]":
           break  # break 表示跳出整个循环

       chunk = json.loads(payload_str)
       delta = chunk["choices"][0]["delta"]
       content = delta.get("content", "")  # 用 get，因为第一块和最后一块可能没有 content
       if chunk.get("usage"):
           tracker.record("deepseek-flash", chunk["usage"])
           continue

       if ttft is None and content:
           ttft = time.perf_counter() - start

       print(content, end="", flush=True)
       full_reply += content  # 累加到完整回复里

elapsed = time.perf_counter() - start

print()                      # 先换个行，因为前面 end="" 没换行
print("完整回复:", full_reply)
print(f"首token延迟: {ttft * 1000:.0f} ms")
print(f"总耗时: {elapsed * 1000:.0f} ms")
tracker.report()
