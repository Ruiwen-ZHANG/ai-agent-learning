"""建库：切块 → 算向量 → 存进 Chroma。语料或切块规则改了才需要重新运行"""
from rag_app import config                                  # 最先导入：HF 镜像设置要先生效
import chromadb
from sentence_transformers import SentenceTransformer

from rag_app.chunker import load_all_chunks

if __name__ == "__main__":
    chunks = load_all_chunks(config.CORPUS_DIR, config.CORPUS_PATTERN)
    print(f"共 {len(chunks)} 块")
    if not chunks:                                          # 一块都没有：语料路径或匹配规则有问题
        raise SystemExit("没有读到任何块，检查 config.CORPUS_DIR")

    texts = [c["text"] for c in chunks]
    model = SentenceTransformer(config.EMBED_MODEL)
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)

    client = chromadb.PersistentClient(path=str(config.DB_DIR))
    try:
        client.delete_collection(config.COLLECTION)         # 先删旧集合，保证是最新的完整索引
    except Exception:                                       # 第一次运行时集合不存在，忽略
        pass                                                # 若因其他原因删除失败，下面 create 会报错暴露
    col = client.create_collection(name=config.COLLECTION, metadata={"hnsw:space": "cosine"})

    col.add(
        ids=[f"chunk-{i}" for i in range(len(chunks))],
        documents=texts,
        embeddings=embeddings.tolist(),
        metadatas=[{"source": c["source"], "heading": c["heading"]} for c in chunks],
    )
    print(f"集合 {config.COLLECTION} 共 {col.count()} 条记录")