import os
from dotenv import load_dotenv
import json
import httpx
import sys
import random
from pathlib import Path
from week7.rag import ask_llm
from week7.chunker import load_all_chunks
from common.cost_tracker import CostTracker

CORPUS_DIR = Path(__file__).parent.parent / "data" / "hello-agents-zh"   # 语料目录
OUT_PATH = Path(__file__).parent.parent / "data" / "eval_set.json"       # 评测集保存位置（data/ 不提交）
PER_FILE = 6                                                              # 每个文件最多抽几块
random.seed(42)                                                           # 固定随机种子：每次运行抽到的块都一样

GEN_PROMPT = """你是评测集出题人。根据下面这段【资料】，出一道检索评测题。

要求：
1. 问题要像真实用户提问：换一种说法，不要照抄资料里的原词，可以口语化
2. 问题必须能用资料中的某一句话回答
3. 问题必须能独立看懂：不能用"这种""上述""文中""该方法"等指代资料里的内容，要写出具体名称
4. evidence 必须从资料中【一字不差】地复制一句话，长度 15 到 60 字，这句话要能回答问题
5. 如果资料不适合出题（比如只有目录、链接、致谢，或者只有代码没有任何说明），返回 {"skip": true}

只输出 JSON，格式：{"question": "...", "evidence": "..."}

【资料】
"""

if __name__ == "__main__":
    tracker = CostTracker()
    chunks = load_all_chunks(CORPUS_DIR, "**/*.md")      # 2512 块
    # 正文（去掉第一行标题路径）至少 150 字才留下，太短的出不了好题
    candidates = [c for c in chunks if len(c["text"].split("\n", 1)[1]) >= 150]

    groups = {}                                           # 键：source（文件名），值：这个文件的块列表
    for c in candidates:
        groups.setdefault(c["source"], []).append(c)      # 没有这个键就先放一个空列表，再把块加进去

    picked = []
    for source, cs in groups.items():  # .items() 同时取出键和值
        picked.extend(random.sample(cs, min(PER_FILE, len(cs))))  # 从这一组里随机抽，不重复

    print(f"共 {len(chunks)} 块，筛选后 {len(candidates)} 块，分成 {len(groups)} 组，抽到 {len(picked)} 块")

    items = []          # 合格的题目
    n_skip = 0          # 模型说"这块不适合出题"的次数
    n_bad = 0           # 不合格的次数：JSON 解析失败，或者 evidence 校验不通过

    LIMIT = None                       # 先试跑 5 块；确认没问题后改成 None，跑全部
    if LIMIT:
        picked = picked[:LIMIT]     # 切片：只取前 5 块

    for i, c in enumerate(picked, 1):                           # i 从 1 开始，用来打印进度
        body = c["text"].split("\n", 1)[1]                      # 撕掉第一行标题路径，只要正文
        msgs = [{"role": "user", "content": GEN_PROMPT + body}]

        try:
            content, usage = ask_llm(msgs, json_mode=True)
        except (httpx.HTTPError, RuntimeError) as e:  # 重试 3 次还是失败，或者 API 返回了错误状态码
            n_bad += 1
            print(f"[{i}] ✗ 调用失败：{e}")
            continue  # 跳过这一块，继续下一块
        tracker.record("deepseek-flash", usage)

        try:
            item = json.loads(content)
        except json.JSONDecodeError:
            n_bad += 1
            print(f"[{i}] ✗ JSON 解析失败：{content[:50]}")
            continue

        if item.get("skip"):                                    # 模型认为这块不适合出题
            n_skip += 1
            print(f"[{i}] - 跳过：{c['heading']}")
            continue

        q = item.get("question", "").strip()                    # 取不到就当空字符串
        ev = item.get("evidence", "").strip()
        # 三个条件都要满足：问题不为空、evidence 是原文里的一句、长度在 15~60 字之间
        if not q or ev not in body or not 15 <= len(ev) <= 60:
             n_bad += 1
             print(f"[{i}] ✗ 校验失败：{ev[:40]}")
             continue

        items.append({
            "question": q,
            "evidence": ev,
            "source": c["source"],  # 答案在哪个文件：判断命中时要用
            "heading": c["heading"],  # 答案在哪一节：bad case 分析时方便定位
        })
        print(f"[{i}] ✓ {q}")

    random.shuffle(items)                                   # 打乱顺序：不让 dev 全是前几章、test 全是后几章
    for n, it in enumerate(items, 1):
        it["id"] = f"q{n:03d}"                              # 编号：q001、q002……
        it["split"] = "dev" if n <= 100 else "test"         # 前 100 题是开发集，其余是测试集

    # 保存成 JSON 文件；ensure_ascii=False 让中文正常显示，indent=2 让文件有缩进、方便人看
    OUT_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    n_dev = len([it for it in items if it["split"] == "dev"])
    print(f"出题 {len(picked)} 块：合格 {len(items)} 题（dev {n_dev} / test {len(items) - n_dev}），"
          f"跳过 {n_skip}，不合格 {n_bad}")
    print(f"已保存到 {OUT_PATH}")
    tracker.report()