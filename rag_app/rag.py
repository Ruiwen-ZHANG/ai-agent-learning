"""RAG 流程：检索 → 拼 prompt → 生成 → 检查引用编号。不加载模型，Retriever 由调用方传进来"""
import re

from rag_app.llm import ask_llm

SYSTEM_PROMPT = """你是 Hello-Agents 教程问答助手。请遵守：
1. 只根据【资料】回答，不要用你自己的知识补充
2. 每个结论后面用 [编号] 标注它来自哪条资料，例如 [1] 或 [1][3]
3. 资料里没有答案时，直接回答"资料中没有相关内容"
4. 资料里的代码可以直接引用"""


def build_context(hits):
    """把检索结果拼成带编号的资料文本"""
    readings = []
    for i, h in enumerate(hits, 1):                          # 编号从 1 开始
        body = h["text"].split("\n", 1)[1]                   # 去掉第一行标题路径，避免和出处重复
        readings.append(f"[{i}] 出处：{h['source']} > {h['heading']}\n{body}")
    return "\n\n".join(readings)


def check_citations(answer, n):
    """找出回答里不合法的引用编号（不在 1~n 之间），返回去重排序后的列表"""
    nums = [int(x) for x in re.findall(r"\[(\d+)\]", answer)]
    return sorted(set(x for x in nums if not 1 <= x <= n))


def answer(question, retriever, tracker=None):
    """回答一个问题，返回字典：回答、出处、不合法编号、usage"""
    hits = retriever.retrieve(question)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},                                 # 固定前缀：命中缓存
        {"role": "user", "content": f"【资料】\n{build_context(hits)}\n\n【问题】\n{question}"},
    ]
    text, usage = ask_llm(messages)
    if tracker is not None:                                  # 想记账就传 tracker，不传也能用
        tracker.record("deepseek-flash", usage)
    return {
        "answer": text,
        "sources": [{"source": h["source"], "heading": h["heading"], "score": h["score"]} for h in hits],
        "bad_citations": check_citations(text, len(hits)),
        "usage": usage,
    }