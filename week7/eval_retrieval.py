import json
from pathlib import Path

from week7.search import search, bm25_search, rrf_search, rerank_search, candidates                 # 要评测的检索函数
from week7.chunker import load_all_chunks        # 可达性检查要用当前的切块

ROOT = Path(__file__).parent.parent
EVAL_PATH = ROOT / "data" / "eval_set.json"
CORPUS_DIR = ROOT / "data" / "hello-agents-zh"
K = 10                                           # 每题检索 10 块

def find_rank(hits, item, section=False):
    """返回正确答案排第几（从 1 开始），没找到返回 None。
    section=False（严格）：必须同文件、并且包含 evidence 原句
    section=True（同节）：同文件同小节的块也算命中
    """
    for rank, h in enumerate(hits, 1):
        if h["source"] != item["source"]:
            continue                                         # 不是同一个文件，跳过这一块
        if item["evidence"] in h["text"]:                    # 严格规则：包含 evidence 原句
            return rank
        if section and h["heading"] == item["heading"]:      # 宽松规则：同一个小节
            return rank
    return None

def evaluate(search_fn, items, k, section=False):
    """用 search_fn 检索每道题，返回 (指标字典, 每题的排名列表)"""
    ranks = []
    for item in items:
        hits = search_fn(item["question"], k=k)          # 调用传进来的检索函数
        ranks.append(find_rank(hits, item,section))

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

    # 三种检索方法依次评测；evaluate 不用改，把不同的检索函数传进去就行
    """methods = {
        "语义": search,
        "BM25": bm25_search,
        #"RRF 1:1": rrf_search,
        #"RRF 1:2": lambda q, k: rrf_search(q, k, w_bm25=2),  # BM25 权重是语义的 2 倍
        #"RRF 1:3": lambda q, k: rrf_search(q, k, w_bm25=3),
        "重排": rerank_search,
    }
    all_ranks = {}  # 记下每种方法每题的排名，后面对比用
    for name, fn in methods.items():
        metrics, ranks = evaluate(fn, reachable, K)
        all_ranks[name] = ranks
        line = "  ".join(f"{m} {v:.1%}" for m, v in metrics.items())
        print(f"{name:8s} {line}")

    for name, fn in [("BM25 前20", lambda q: bm25_search(q, 20)),
                     ("语义 前20", lambda q: search(q, 20)),
                     ("并集", candidates)]:
        found = sum(1 for it in reachable if find_rank(fn(it["question"]), it) is not None)
        print(f"{name:8s} 召回率 {found / len(reachable):.1%}")

    # 重排后没进前 3 的题：RAG 实际只取前 3 块，这些题拿不到正确资料，是 bad case 分析的素材
    print("重排后没进前 3 的题：")
    for it, r in zip(reachable, all_ranks["重排"]):
        if r is None or r > 3:  # 没找到，或者排在第 4 名以后
            print(f"  {it['id']} | 排名 {r} | {it['question']}")"""

    # 严格规则 vs 同节规则：同一节被切成几块时，别的块也能回答问题，严格规则会误判
    for label, sec in [("重排（严格）", False), ("重排（同节）", True)]:
        metrics, _ = evaluate(rerank_search, reachable, K, section=sec)
        line = "  ".join(f"{m} {v:.1%}" for m, v in metrics.items())
        print(f"{label:10s} {line}")
