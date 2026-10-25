import os                                      # os：操作系统相关功能，这里用来设环境变量
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"   # os.environ 是一个字典，存放所有环境变量
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"   # 关掉 Windows 符号链接警告，纯属让输出干净些

from sentence_transformers import SentenceTransformer  # 一定写在上面两行之后

model = SentenceTransformer("BAAI/bge-small-zh-v1.5")

print("模型加载完成")

# ---------- 第 3 步：准备数据 ----------
# docs：待检索的"文档库"，前 5 句来自第 4、5 周笔记，最后 1 句是完全无关的干扰项
docs = [
    "工具执行完后，要用 role 为 tool 的消息把结果回填，并带上对应的 tool_call_id",
    "arguments 字段是 JSON 字符串，必须先用 json.loads 解析成字典",
    "messages 多套了一层方括号，接口返回 422 错误",
    "Docker 镜像构建时用 .dockerignore 排除 .env 文件",
    "temperature 设为 0 可以让输出尽量稳定，便于做对照实验",
    "今天食堂的麻辣香锅排队的人特别多",
]

# query：用户的问题，是一个字符串（不是列表）
# 先用 Q1，跑完再改成 Q2、Q3
query = "422"

doc_vecs = model.encode(docs,normalize_embeddings=True)
query_vec = model.encode([query],normalize_embeddings=True)

print(doc_vecs.shape)
print(query_vec.shape)

scores = (query_vec @ doc_vecs.T) [0]
print(scores)

result = sorted(zip(scores, docs), reverse=True)

for score, doc in result:
    print(f"{score:.4f} {doc}")