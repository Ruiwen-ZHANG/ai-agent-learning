import httpx
import time

params={"city": "北京", "keyword": "AI Agent"}
try:
    r = httpx.get("https://httpbin.org/get", params=params,timeout=10)
    r.raise_for_status()
    data = r.json()
    print(data)
    print("状态码:", r.status_code)
    print(r.url)
except httpx.TimeoutException:
    print("请求超时")
except httpx.HTTPStatusError as e:
    print(f"HTTP {e.response.status_code}: {e.response.text}")
except httpx.RequestError as e:
    print(f"网络错误: {e}")
else:
    print(data.get("result", "响应中没有 result 字段"))


payload = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"},
    ],
    "temperature": 0.7,
}

r=httpx.post("https://httpbin.org/post", json=payload)

print("状态码:", r.status_code)
print("发出去的 JSON:", r.json()["json"])
print("Content-Type:", r.json()["headers"]["Content-Type"])

headers = {"Authorization": "Bearer sk-test-12345"}
r = httpx.get("https://httpbin.org/headers", headers=headers,timeout=5)
print(r.json())

# 第一段：不调 raise_for_status，看它会不会抛异常
r = httpx.get("https://httpbin.org/status/404", timeout=10)
print("状态码:", r.status_code)
print("程序还在跑，没有抛异常")

# 第二段：调 raise_for_status，用 try/except 捕获
try:
    r = httpx.get("https://httpbin.org/status/404", timeout=10)
    r.raise_for_status()
    print("这行不会执行")
except httpx.HTTPStatusError as e:
    print(f"捕获到: {e.response.status_code}")


# 第一段：timeout 太短
try:
    r = httpx.get("https://httpbin.org/delay/5", timeout=2)
    print("不会执行到这里")
except httpx.TimeoutException:
    print("超时了，符合预期")

# 第二段：timeout 够长
try:
    r = httpx.get("https://httpbin.org/delay/5", timeout=10)
    print("成功，状态码:", r.status_code)
except httpx.TimeoutException:
    print("还是超时？可能是网络太慢")

start = time.time()
try:
    r = httpx.get("https://httpbin.org/delay/5", timeout=2)
except httpx.TimeoutException:
    print(f"超时了，实际等了 {time.time() - start:.2f} 秒")

url = "https://httpbin.org/get"

# 方式 A：每次新建连接
start = time.time()
for _ in range(3):
    httpx.get(url, timeout=10)
print(f"独立请求 3 次: {time.time() - start:.2f} 秒")

# 方式 B：复用连接
start = time.time()
with httpx.Client(timeout=10) as client:
    for _ in range(3):
        client.get(url)
print(f"复用连接 3 次: {time.time() - start:.2f} 秒")


def request_with_retry(url: str, max_retries: int = 3) -> dict:
    """带指数退避的请求。

    429 和 5xx 会重试，4xx（除 429）直接抛出。
    """
    for attempt in range(max_retries):
        # 你来实现：
        # 1. try 里发请求
        try:
           r = httpx.get(url, timeout=10)
           #  data = r.json()2. 如果状态码是 429 或 >= 500，等待 2**attempt 秒后 continue
           if r.status_code == 429 or r.status_code >= 500:
               wait = 2**attempt
               print(f"第 {attempt + 1} 次失败({r.status_code})，{wait} 秒后重试")
               time.sleep(wait)
               continue
               # 3. 其他情况调 raise_for_status()，成功就 return r.json()
           r.raise_for_status()
           return r.json()

        # 4. 捕获 TimeoutException，同样退避重试
        except httpx.TimeoutException:
          wait = 2**attempt
          print(f"第 {attempt + 1} 次超时，{wait} 秒后重试")
          time.sleep(wait)

    # 循环跑完还没成功，说明重试次数用尽
    raise RuntimeError(f"重试 {max_retries} 次后仍失败: {url}")

try:
    request_with_retry("https://httpbin.org/status/503")
except RuntimeError as e:
    print("最终失败:", e)