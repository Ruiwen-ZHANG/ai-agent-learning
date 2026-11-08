# 使用方式（在项目根目录执行）：docker build -f rag_app/Dockerfile -t rag-app .
# 注意：Dockerfile 的注释只能单独占一行，不能写在指令后面

# ① 基础镜像：Python 3.14 精简版，和本机 Python 版本一致
#    如果后面某个库安装失败（No matching distribution），把 3.14 换成 3.12 再试
FROM python:3.14-slim

# ② 容器里的工作目录：后面所有命令都在 /app 下执行
#    config.py 的 ROOT = Path(__file__).parent.parent 会自动变成 /app
WORKDIR /app

# ③ 让 print 和日志立刻输出，docker logs 才能及时看到
ENV PYTHONUNBUFFERED=1

# ④ 单独安装 CPU 版 torch（版本和本机一致）：默认的 GPU 版会多下载好几 GB 用不到的 CUDA 库
#    放在最前面：最慢、几乎不变，层缓存能一直复用
RUN pip install --no-cache-dir torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu

# ⑤⑥ 先只复制依赖清单，再安装其他依赖
#     只要 requirements.txt 不变，改代码后重新 build 不会重装依赖
COPY rag_app/requirements.txt rag_app/requirements.txt
RUN pip install --no-cache-dir -r rag_app/requirements.txt

# ⑦ 只复制下载模型需要的 3 个文件（不复制整个 rag_app）
#    这样改 api.py、index.html 时，第 ⑧ 步下载模型不会重做
#    复制多个文件时，最后一项是目标目录，必须以 / 结尾
COPY rag_app/__init__.py rag_app/config.py rag_app/download_models.py rag_app/

# ⑧ 联网下载两个模型，存进镜像
#    HF_HUB_OFFLINE=0 只对这一条命令有效；运行时 config.py 会默认设为 1（离线）
RUN HF_HUB_OFFLINE=0 python -m rag_app.download_models

# ⑨ 复制本机建好的向量库（2505 块），容器里不重新建库
COPY chroma_db chroma_db

# ⑩ 最后复制全部代码：最常改，放在最下面，改了只重做这一层
COPY rag_app rag_app

# ⑪ 说明容器使用 8000 端口（真正开窗靠 docker run 的 -p）
EXPOSE 8000

# ⑫ 容器启动时执行：用 uvicorn 运行 rag_app/api.py 里的 app
#    --host 0.0.0.0：接受来自容器外面的请求，不能用默认的 127.0.0.1
CMD ["uvicorn", "rag_app.api:app", "--host", "0.0.0.0", "--port", "8000"]