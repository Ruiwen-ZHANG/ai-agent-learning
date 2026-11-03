"""调用 DeepSeek。只负责发请求、重试、返回结果，不打印回答、不记账、不加载任何模型"""
import os
import time

import httpx
from dotenv import load_dotenv

from rag_app.config import LLM_MODEL, LLM_URL

load_dotenv()                                        # 从项目根目录的 .env 读取环境变量
API_KEY = os.getenv("DEEPSEEK_API_KEY")              # ← 改成你 .env 里实际用的变量名
if not API_KEY:                                      # 启动时就检查，比调用时才报 401 更容易排查
    raise RuntimeError("没有读到 API Key，请检查 .env 文件")

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def ask_llm(messages, json_mode=False, max_tokens=1000):
    """调用 DeepSeek，返回 (回答文本, usage)；网络错误重试 3 次，仍失败就 raise 给调用方"""
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0,                            # RAG 要忠实于资料，不需要发挥
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},
    }
    if json_mode:                                    # 需要 JSON 输出时才加；prompt 里必须出现 "json"
        payload["response_format"] = {"type": "json_object"}

    response = None
    for attempt in range(3):                         # 最多试 3 次
        try:
            response = httpx.post(LLM_URL, headers=HEADERS, json=payload, timeout=30)
            break                                    # 成功就跳出
        except (httpx.TimeoutException, httpx.RequestError) as e:
            if attempt == 2:                         # 第 3 次还失败
                raise                                # 原样抛出，由调用方决定怎么处理
            time.sleep(2 ** attempt)                 # 指数退避：等 1 秒、2 秒

    if response.status_code != 200:
        raise RuntimeError(f"API 返回 {response.status_code}：{response.text[:200]}")

    data = response.json()
    choice = data["choices"][0]
    if choice["finish_reason"] == "length":          # 被 max_tokens 截断
        print("⚠ 回答被截断，可以调大 max_tokens")
    return choice["message"]["content"], data["usage"]