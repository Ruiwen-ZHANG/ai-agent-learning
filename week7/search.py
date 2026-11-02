import os
import re
import jieba                          # 中文分词
from rank_bm25 import BM25Okapi       # BM25 打分；Okapi 是 BM25 最常用的那个版本
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

def tokenize(text):
    """中文分词（搜索引擎模式），转小写，去掉标点和空白"""
    return [w.lower() for w in jieba.lcut_for_search(text) if re.search(r"\w", w)]

ROOT = Path(__file__).parent.parent        # __file__ 是 search_index.py 本身；parent 是 week7/，再一个 parent 是项目根目录
DB_DIR = ROOT / "chroma_db"

model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
from sentence_transformers import CrossEncoder      # 交叉编码器（这一行可以放到文件开头的 import 里）

reranker = CrossEncoder("BAAI/bge-reranker-base", max_length=512)   # 问题+块拼起来最多读 512 个 token
client = chromadb.PersistentClient(path=str(DB_DIR))
COLLECTION = "hello_agents"                  # 和 build_index.py 里的集合名一致

col = client.get_collection(COLLECTION)

# 从 Chroma 里取出全部块，不用重新切块，保证和向量库里的块完全一致
_all = col.get(include=["documents", "metadatas"])
BM25_IDS = _all["ids"]
BM25_DOCS = _all["documents"]
BM25_METAS = _all["metadatas"]
bm25 = BM25Okapi([tokenize(d) for d in BM25_DOCS])    # 每块分词后交给 BM25 建索引


def search(query, k=3):
    query_vec = model.encode([query], normalize_embeddings=True)

    res = col.query(query_embeddings=query_vec.tolist(), n_results=k)

    hits = []  # 结果列表：每个元素是一张卡片的信息
    # zip 把三个字段按位置配对；每个字段先取 [0]，因为只查了一个问题
    for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({
            "id": cid,
            "text": doc,  # 原文
            "source": meta["source"],  # 出自哪个文件
            "heading": meta["heading"],  # 出自哪一节
            "score": 1 - dist,  # 余弦距离 → 余弦相似度，越大越相关（和 §2 方向一致）
            "via": "语义",
        })
    return hits

def extract_keywords(question):
    """从问题里挑出专有标识符：含数字、下划线或点，且至少 3 个字符（如 422、tool_call_id、json.loads）"""
    tokens = re.findall(r"[A-Za-z0-9_.]{3,}", question)    # 先找出所有连续 3 个以上的英文、数字、下划线、点
    return [t for t in tokens if any(ch.isdigit() or ch in "_." for ch in t)]   # 再只保留含数字、_ 或 . 的

def keyword_search(keyword, limit=2):
    """找原文里字面包含 keyword 的块，最多 limit 块"""
    res = col.get(where_document={"$contains": keyword}, limit=limit)
    hits = []
    for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):   # 注意：get 的结果不用取 [0]
        hits.append({
            "id": cid,
            "text": doc,
            "source": meta["source"],
            "heading": meta["heading"],
            "score": None,              # 字面匹配没有相似度
            "via": "关键词",
        })
    return hits

def hybrid_search(question, k=3):
    """语义检索 top-k，再补上关键词命中的块（去重）"""
    hits = search(question, k)                        # 第 1 路：语义
    seen = {h["id"] for h in hits}                    # 已经有的编号（集合推导式，查找很快）

    for kw in extract_keywords(question):             # 第 2 路：每个关键词
        for h in keyword_search(kw):
            if h["id"] not in seen:                   # 语义检索已经找到的，不重复加
                hits.append(h)
                seen.add(h["id"])
    return hits

def bm25_search(query, k=10):
    """BM25 关键词检索，返回分数最高的 k 块（格式和 search 一致）"""
    scores = bm25.get_scores(tokenize(query))       # 问题对每一块的 BM25 分数，numpy 数组，长度 2505
    top = scores.argsort()[::-1][:k]                # 从高到低排序后，取前 k 个的下标
    hits = []
    for i in top:
        hits.append({
            "id": BM25_IDS[i],
            "text": BM25_DOCS[i],
            "source": BM25_METAS[i]["source"],
            "heading": BM25_METAS[i]["heading"],
            "score": float(scores[i]),              # numpy 的数字转成普通 float
            "via": "BM25",
        })
    return hits

def rrf_search(question, k=10, pool=20, w_sem=1.0, w_bm25=1.0):
    """语义检索 + BM25 各取 pool 块，用加权 RRF 融合，返回前 k 块"""
    rrf = {}
    by_id = {}
    # 每一路带上自己的权重
    for w, hits in ((w_sem, search(question, pool)), (w_bm25, bm25_search(question, pool))):
        for rank, h in enumerate(hits, 1):
            rrf[h["id"]] = rrf.get(h["id"], 0) + w / (60 + rank)    # 原来是 1 /，现在是 w /
            by_id.setdefault(h["id"], h)

    top_ids = sorted(rrf, key=rrf.get, reverse=True)[:k]                  # 按 RRF 分数从高到低取前 k
    return [{**by_id[i], "score": rrf[i], "via": "RRF"} for i in top_ids]

def candidates(question, pool=20):
    """召回：BM25 前 pool 块 + 语义前 pool 块，按 id 去重后合并（并集）"""
    seen = set()
    result = []
    for h in bm25_search(question, pool) + search(question, pool):   # 两个列表用 + 拼起来，BM25 的在前
        if h["id"] not in seen:                                     # 两路都找到的块只保留一次
            seen.add(h["id"])
            result.append(h)
    return result

def rerank_search(question, k=10, pool=20):
    """两阶段检索：先召回并集，再用 reranker 给每一块打分，取前 k"""
    cands = candidates(question, pool)
    pairs = [(question, h["text"]) for h in cands]           # 每一块和问题配成一对
    scores = reranker.predict(pairs, batch_size=16)          # 每一对得到一个相关度分数
    order = scores.argsort()[::-1][:k]                       # 分数从高到低，取前 k 个的下标
    return [{**cands[i], "score": float(scores[i]), "via": "rerank"} for i in order]

if __name__ == "__main__":
    while True:
        q = input("\n问题（直接回车退出）：").strip()  # 等待输入一行；strip 去掉首尾空格
        if not q:  # 空字符串 → 直接按了回车
            break  # 跳出循环，程序结束

        hits = search(q)
        for rank, h in enumerate(hits, 1):  # 从 1 开始编号
            print(f"{rank}. {h['score']:.4f} | {h['source']} | {h['heading']}")
            print("   " + h["text"][:150].replace("\n", " "))  # 只显示前 150 字，换行替换成空格，显示更整齐