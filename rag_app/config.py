"""rag_app 的全部配置。会随部署环境变化的值都可以用环境变量覆盖（统一加 RAG_ 前缀）"""
import os
from pathlib import Path

# ---------- HuggingFace 下载设置：必须在任何文件 import sentence_transformers 之前执行 ----------
# setdefault：环境变量里已经设置了就不覆盖，没设置才用这里的值（Docker 里可以改成联网下载）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")        # 国内镜像
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")       # 关掉 Windows 符号链接警告
os.environ.setdefault("HF_HUB_OFFLINE", "1")                        # 模型已缓存，只读本地，不联网检查

# ---------- 路径 ----------
ROOT = Path(__file__).parent.parent                                  # config.py → rag_app/ → 项目根目录
CORPUS_DIR = Path(os.getenv("RAG_CORPUS_DIR", str(ROOT / "data" / "hello-agents-zh")))   # 语料目录
CORPUS_PATTERN = "**/*.md"                                           # 递归匹配所有 md
DB_DIR = Path(os.getenv("RAG_DB_DIR", str(ROOT / "chroma_db")))      # Chroma 数据库文件夹
COLLECTION = "hello_agents"                                          # 集合名：整个项目只在这里定义一次

# ---------- 切块（第 7 周确定） ----------
MAX_CHARS = 450                     # 每块正文字数上限
MAX_CODE = 1500                     # 代码块超过这个长度就在内部空行处拆开

# ---------- 模型 ----------
EMBED_MODEL = "BAAI/bge-small-zh-v1.5"     # 向量模型：建库和查询必须是同一个
RERANK_MODEL = "BAAI/bge-reranker-base"    # 重排模型

# ---------- 检索参数（第 8 周延迟实验确定的部署配置 D） ----------
# pool10 + len256：比 pool20 + len512 快约 2.9 倍，dev Hit@3 少 2 题；有 GPU 时可改回 20 / 512
POOL = int(os.getenv("RAG_POOL", "10"))                      # 召回时 BM25 和语义各取几块
RERANK_MAX_LEN = int(os.getenv("RAG_RERANK_MAX_LEN", "256"))  # reranker 每块最多读多少 token
TOP_K = int(os.getenv("RAG_TOP_K", "3"))                      # 最终交给大模型的块数

# ---------- 大模型 ----------
LLM_MODEL = os.getenv("RAG_LLM_MODEL", "deepseek-flash")     # 连字符，不是下划线
LLM_URL = "https://api.deepseek.com/v1/chat/completions"
# API Key 不放在这里：config.py 会提交到 GitHub，Key 只放在 .env，由 llm.py 读取