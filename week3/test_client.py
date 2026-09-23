import httpx
import time

r = httpx.get("http://127.0.0.1:8000/users/123")
print(r.status_code, r.json())

r = httpx.get("http://127.0.0.1:8000/users/999")
print(r.status_code, r.json())

payload = {
    "messages": [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"},
    ]
}

r = httpx.post("http://127.0.0.1:8000/chat", json=payload)
print(r.status_code, r.json())

# 故意传错
bad = {"messages": [{"role": "User", "content": "你好"}]}
r = httpx.post("http://127.0.0.1:8000/chat", json=bad)
print(r.status_code, r.json())

print("--- 流式接收 ---")

start = time.time()
with httpx.stream("GET", "http://127.0.0.1:8000/stream", timeout=30) as r:
    for line in r.iter_lines():
        if not line.startswith("data: "):
            continue
        content = line[6:]
        if content == "[DONE]":
            break
        print(f"[{time.time() - start:.2f}s] {content}")

print()
print("--- 接收完毕 ---")