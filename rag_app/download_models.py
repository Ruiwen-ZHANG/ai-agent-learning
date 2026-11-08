"""Docker build 时运行一次：下载向量模型和重排模型，存进镜像里的 HuggingFace 缓存。

运行方式（写在 Dockerfile 里）：HF_HUB_OFFLINE=0 python -m rag_app.download_models
命令前面的 HF_HUB_OFFLINE=0 允许联网；config.py 用的是 setdefault，看到已经有值就不会改成 1
"""
# 必须第一个导入：config.py 负责设置 HF 镜像地址（hf-mirror.com），并提供两个模型的名字
from rag_app import config

# 必须在 config 之后导入：HF 的环境变量要在 sentence_transformers 被导入之前设置好
from sentence_transformers import SentenceTransformer, CrossEncoder

print(f"开始下载向量模型：{config.EMBED_MODEL}")
SentenceTransformer(config.EMBED_MODEL)          # 创建模型时，本地没有就自动下载到缓存

print(f"开始下载重排模型：{config.RERANK_MODEL}")
CrossEncoder(config.RERANK_MODEL)                # 同上；运行时 retriever.py 会从缓存里读取

print("模型下载完成")