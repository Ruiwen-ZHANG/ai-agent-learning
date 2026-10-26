import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent        # __file__ 是 search_index.py 本身；parent 是 week6/，再一个 parent 是项目根目录
DB_DIR = ROOT / "chroma_db"

model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
client = chromadb.PersistentClient(path=str(DB_DIR))
col = client.get_collection("notes")

def search(query, k=3):
    query_vec = model.encode([query], normalize_embeddings=True)

    res = col.query(query_embeddings=query_vec.tolist(), n_results=k)

    hits = []  # 结果列表：每个元素是一张卡片的信息
    # zip 把三个字段按位置配对；每个字段先取 [0]，因为只查了一个问题
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({
            "text": doc,  # 原文
            "source": meta["source"],  # 出自哪个文件
            "heading": meta["heading"],  # 出自哪一节
            "score": 1 - dist,  # 余弦距离 → 余弦相似度，越大越相关（和 §2 方向一致）
        })
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