import os
import re                                   # 正则表达式，第 5 步用来找回答里的 [编号]
import requests
from dotenv import load_dotenv
import json
import httpx
import sys

from week7.search import hybrid_search             # §4 写的检索函数
from common.cost_tracker import CostTracker # 第 4 周写、本周升级的计费器

load_dotenv()                               # 从 .env 读取 API Key
key = os.getenv("DEEPSEEK_API_KEY")

if not key:
    raise ValueError("未找到 DEEPSEEK_API_KEY，请检查项目根目录下的 .env 文件")

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {key}"
}

url = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-flash"
SYSTEM_PROMPT = """你是学习笔记问答助手。请遵守：
1. 只根据【资料】回答，不要用你自己的知识补充
2. 每个结论后面用 [编号] 标注它来自哪条资料，例如 [1] 或 [1][3]
3. 资料里没有答案时，直接回答"笔记中没有相关内容"
4. 资料里的代码可以直接引用"""

tracker = CostTracker()  # 括号表示调用，这一步会执行 __init__

def build_context(hits):
    readings = []
    for i,h in enumerate(hits,1):
        body = h["text"].split("\n", 1)[1]  # 只在第一个换行处切一刀，取后半部分
        reading = f"[{i}] 出处：{h['source']} > {h['heading']}\n{body}"
        readings.append(reading)
    return "\n\n".join(readings)

def ask_llm(messages):

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 1000,
        "thinking": {"type": "disabled"},
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

    choice = data["choices"][0]

    if choice["finish_reason"] == "length":  # 回答因为 max_tokens 不够被截断了
        print("回答被截断，可以调大 max_tokens")
    return choice["message"]["content"], data["usage"]


def check_citations(answer,n):
    nums = re.findall(r"\[(\d+)\]", answer)
    nums = [int(x) for x in nums]
    bad = [x for x in nums if not 1 <= x <= n]
    return sorted(set(bad))

def rag(question,tracker):
    hits = hybrid_search(question,k=3)
    context = build_context(hits)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"【资料】\n{context}\n\n【问题】\n{question}"},
    ]
    answer, usage = ask_llm(messages)
    tracker.record(MODEL,usage)
    return answer, hits

if __name__ == "__main__":
    tracker = CostTracker()

    while True:
        q = input("\n问题（直接回车退出）：").strip()  # 等待输入一行；strip 去掉首尾空格
        if not q:  # 空字符串 → 直接按了回车
            break  # 跳出循环，程序结束

        answer, hits = rag(q,tracker)
        print("\n【回答】")
        print(answer)
        print("\n【出处】")
        for i, h in enumerate(hits, 1):
            if h["score"] is None:
                print(f"[{i}] {h['source']} > {h['heading']}（关键词命中）")
            else:
                print(f"[{i}] {h['source']} > {h['heading']}（相似度 {h['score']:.4f}）")

        bad = check_citations(answer,len(hits))
        if bad:
            print(f"回答中存在不合法编号{bad}")

    tracker.report()