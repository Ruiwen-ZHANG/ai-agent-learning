import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
from week6.chunker import load_all_chunks   # 和 common.cost_tracker 的导入方式一样，从项目根目录开始写

ROOT = Path(__file__).parent.parent        # __file__ 是 build_index.py 本身；parent 是 week6/，再一个 parent 是项目根目录
DB_DIR = ROOT / "chroma_db"

chunks = load_all_chunks(ROOT)                 # 完整的块字典，后面还要取 source 和 heading
print(f"共 {len(chunks)} 块")
texts = [c["text"] for c in chunks]            # 只取出文本，交给模型编码

model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)   # 归一化后点积就是余弦相似度
print(f"向量形状：{embeddings.shape}")

client = chromadb.PersistentClient(path=str(DB_DIR))   # 连接硬盘上的数据库文件夹，不存在就自动创建；path 要传字符串
try:
    client.delete_collection("notes")     # 删除旧集合
except Exception:                          # 第一次运行时集合还不存在，删除会报错，忽略即可
    pass
col = client.create_collection(
    name="notes",                                      # 集合的名字，查询时用同一个名字打开
    metadata={"hnsw:space": "cosine"},                 # 用余弦距离（不写的话默认是 L2 欧氏距离）
)

ids = [f"chunk-{i}" for i, c in enumerate(chunks)]     # 每块一个唯一编号：chunk-0、chunk-1……（必须是字符串）
metadatas = [{"source": c["source"], "heading": c["heading"]} for c in chunks]   # 出处信息，查询时会一起返回

col.add(
    ids=ids,                          # 编号
    documents=texts,                  # 原文
    embeddings=embeddings.tolist(),   # 向量：numpy 数组转成普通列表
    metadatas=metadatas,              # 出处
)                                     # 四个列表长度必须相同，第 i 个元素都描述第 i 块

print(f"集合里共有 {col.count()} 条记录")
