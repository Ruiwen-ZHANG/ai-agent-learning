"""检索：把模型、向量库、BM25 索引都包在 Retriever 类里，创建对象时才加载（import 时不加载）"""
import re

import chromadb
import jieba
from rank_bm25 import BM25Okapi

from rag_app import config                           # 先导入 config，保证 HF 镜像设置最先生效
from sentence_transformers import SentenceTransformer, CrossEncoder


def tokenize(text):
    """中文分词（搜索引擎模式），转小写，去掉标点和空白；建 BM25 索引和查询必须用同一个"""
    return [w.lower() for w in jieba.lcut_for_search(text) if re.search(r"\w", w)]


class Retriever:
    """两阶段检索：BM25 + 语义召回取并集，再用 reranker 重排"""

    def __init__(self):
        """加载所有模型和索引。较慢（十几秒），整个程序只应创建一次"""
        self.model = SentenceTransformer(config.EMBED_MODEL)                       # 向量模型
        self.reranker = CrossEncoder(config.RERANK_MODEL, max_length=config.RERANK_MAX_LEN)   # 重排模型
        client = chromadb.PersistentClient(path=str(config.DB_DIR))
        self.col = client.get_collection(config.COLLECTION)                        # 不存在就报错：提醒先建库

        # BM25 索引：从 Chroma 取全部块，保证和向量库是同一批、编号一一对应
        data = self.col.get(include=["documents", "metadatas"])
        self.ids = data["ids"]
        self.docs = data["documents"]
        self.metas = data["metadatas"]
        self.bm25 = BM25Okapi([tokenize(d) for d in self.docs])

    def search(self, query, k):
        """语义检索：返回最相似的 k 块"""
        vec = self.model.encode([query], normalize_embeddings=True)                # 和建库时同样归一化
        res = self.col.query(query_embeddings=vec.tolist(), n_results=k)
        return [{"id": cid, "text": doc, "source": meta["source"],
                 "heading": meta["heading"], "score": 1 - dist}                   # 余弦距离 → 相似度
                for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                                res["metadatas"][0], res["distances"][0])]

    def bm25_search(self, query, k):
        """BM25 关键词检索：返回分数最高的 k 块"""
        scores = self.bm25.get_scores(tokenize(query))
        top = scores.argsort()[::-1][:k]                                           # 从高到低取前 k 个下标
        return [{"id": self.ids[i], "text": self.docs[i], "source": self.metas[i]["source"],
                 "heading": self.metas[i]["heading"], "score": float(scores[i])} for i in top]

    def candidates(self, query, pool=None):
        """召回：BM25 前 pool 块 + 语义前 pool 块，按 id 去重后合并"""
        pool = pool or config.POOL                                                 # 不传就用配置值
        seen, result = set(), []
        for h in self.bm25_search(query, pool) + self.search(query, pool):
            if h["id"] not in seen:
                seen.add(h["id"])
                result.append(h)
        return result

    def retrieve(self, query, k=None):
        """完整两阶段检索：召回并集 → reranker 打分 → 取前 k 块"""
        k = k or config.TOP_K
        cands = self.candidates(query)
        scores = self.reranker.predict([(query, h["text"]) for h in cands], batch_size=16)
        order = scores.argsort()[::-1][:k]
        return [{**cands[i], "score": float(scores[i])} for i in order]           # score 换成重排分数