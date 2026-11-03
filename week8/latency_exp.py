import json
import time
from pathlib import Path

from sentence_transformers import CrossEncoder
from week7.search import candidates, reranker as reranker_512      # week7 里那个 max_length=512 的，导入时改个名字
from week7.eval_retrieval import find_rank                          # 复用上周的命中判断

ROOT = Path(__file__).parent.parent
EVAL_PATH = ROOT / "data" / "eval_set.json"
K = 10

reranker_256 = CrossEncoder("BAAI/bge-reranker-base", max_length=256)   # 同一个模型，只读前 256 个 token

def make_rerank(model, pool):
    """按给定的 reranker 和召回数量，造一个检索函数"""
    def search_fn(question, k=K):
        cands = candidates(question, pool)                       # 用外层传进来的 pool
        scores = model.predict([(question, h["text"]) for h in cands], batch_size=16)   # 用外层传进来的 model
        order = scores.argsort()[::-1][:k]
        return [{**cands[i], "score": float(scores[i])} for i in order]
    return search_fn                                             # 返回的是函数本身，不加括号


configs = {
    "A pool20 len512": make_rerank(reranker_512, 20),
    "B pool10 len512": make_rerank(reranker_512, 10),
    "C pool20 len256": make_rerank(reranker_256, 20),
    "D pool10 len256": make_rerank(reranker_256, 10),
}

if __name__ == "__main__":
    items = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    # dev = [it for it in items if it["split"] == "dev"]      # 上周确认过 dev 91 题全部可达，这里不再检查
    #
    # for name, fn in configs.items():
    #     t0 = time.perf_counter()
    #     hit_lists = [fn(it["question"]) for it in dev]       # 检索只跑一次，结果存起来
    #     avg_t = (time.perf_counter() - t0) / len(dev)
    #
    #     for rule, sec in [("严格", False), ("同节", True)]:
    #         ranks = [find_rank(h, it, sec) for h, it in zip(hit_lists, dev)]
    #         n = len(ranks)
    #         hit3 = sum(1 for r in ranks if r is not None and r <= 3) / n
    #         mrr = sum(1 / r for r in ranks if r is not None) / n
    #         print(f"{name}  {rule}  Hit@3 {hit3:.1%}  MRR {mrr:.1%}")
    #     print(f"{name}  平均每题 {avg_t:.2f} 秒\n")

    # 部署配置 D 在 test 上确认一次（test 第二次使用：上周验证 A，本周验证 D）
    test = [it for it in items if it["split"] == "test"]
    fn = configs["D pool10 len256"]
    t0 = time.perf_counter()
    hit_lists = [fn(it["question"]) for it in test]
    avg_t = (time.perf_counter() - t0) / len(test)
    for rule, sec in [("严格", False), ("同节", True)]:
        ranks = [find_rank(h, it, sec) for h, it in zip(hit_lists, test)]
        n = len(ranks)
        hit3 = sum(1 for r in ranks if r is not None and r <= 3) / n
        mrr = sum(1 / r for r in ranks if r is not None) / n
        print(f"test D  {rule}  Hit@3 {hit3:.1%}  MRR {mrr:.1%}")
    print(f"test D  平均每题 {avg_t:.2f} 秒")