import re
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent        # __file__ 是 search_index.py 本身；parent 是 week7/，再一个 parent 是项目根目录
DB_DIR = ROOT / "chroma_db"

model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
client = chromadb.PersistentClient(path=str(DB_DIR))
col = client.get_collection("notes")

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

if __name__ == "__main__":
    while True:
        q = input("\n问题（直接回车退出）：").strip()  # 等待输入一行；strip 去掉首尾空格
        if not q:  # 空字符串 → 直接按了回车
            break  # 跳出循环，程序结束

        hits = search(q)
        for rank, h in enumerate(hits, 1):  # 从 1 开始编号
            print(f"{rank}. {h['score']:.4f} | {h['source']} | {h['heading']}")
            print("   " + h["text"][:150].replace("\n", " "))  # 只显示前 150 字，换行替换成空格，显示更整齐