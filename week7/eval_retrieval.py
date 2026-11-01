import json
from pathlib import Path

from week7.search import search                  # 要评测的检索函数
from week7.chunker import load_all_chunks        # 可达性检查要用当前的切块

ROOT = Path(__file__).parent.parent
EVAL_PATH = ROOT / "data" / "eval_set.json"
CORPUS_DIR = ROOT / "data" / "hello-agents-zh"
K = 10                                           # 每题检索 10 块

def find_rank(hits, item):
    """返回正确答案在检索结果里排第几（从 1 开始）；不在结果里返回 None"""
    for rank, h in enumerate(hits, 1):
        if h["source"] == item["source"] and item["evidence"] in h["text"]:
            return rank                  # 找到第一个就返回：只关心排得最靠前的那个
    return None                          # 循环跑完都没找到

def evaluate(search_fn, items, k):
    """用 search_fn 检索每道题，返回 (指标字典, 每题的排名列表)"""
    ranks = []
    for item in items:
        hits = search_fn(item["question"], k=k)          # 调用传进来的检索函数
        ranks.append(find_rank(hits, item))

    n = len(ranks)
    metrics = {}
    for cut in (1, 3, 5, 10):                            # Hit@1、Hit@3、Hit@5、Hit@10
        metrics[f"Hit@{cut}"] = sum(1 for r in ranks if r is not None and r <= cut) / n
    metrics["MRR"] = sum(1 / r for r in ranks if r is not None) / n
    return metrics, ranks

if __name__ == "__main__":
    items = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    dev = [it for it in items if it["split"] == "dev"]
    chunks = load_all_chunks(CORPUS_DIR, "**/*.md")
    reachable = []
    for it in dev:
        # 当前切块里，至少有一块和题目同一个文件、并且包含 evidence
        if any(c["source"] == it["source"] and it["evidence"] in c["text"] for c in chunks):
            reachable.append(it)
        else:
            print(f"不可达：{it['id']} {it['evidence'][:30]}")
    print(f"dev 共 {len(dev)} 题，可达 {len(reachable)} 题")

    metrics, ranks = evaluate(search, reachable, K)
    print("语义检索（baseline）：")
    for name, value in metrics.items():
        print(f"  {name}: {value:.1%}")  # :.1% → 百分比，保留 1 位小数

    # 没进前 10 的题：bad case 分析的素材
    print("没找到的题：")
    for it, r in zip(reachable, ranks):
        if r is None:
            print(f"  {it['id']} | {it['question']}")