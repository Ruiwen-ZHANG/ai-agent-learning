from ast import List
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import httpx
from rag_app.retriever import Retriever
from rag_app.rag import answer

class AskRequest(BaseModel):
    question: str = Field(max_length=500, min_length=1)

class Source(BaseModel):
    source: str
    heading: str
    score: float

class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    bad_citations: list[int]
    usage: dict

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.retriever = Retriever()
    yield

app = FastAPI(title="Hello-Agents RAG 问答", lifespan=lifespan)

@app.get("/health")
def health():
    # 判断 app.state 上有没有 retriever
    hasattr(app.state,"retriever")
    # 有：返回 {"status": "ok"}
    if hasattr(app.state,"retriever"):
        return {"status": "ok"}
    # 没有：返回 {"status": "loading"}
    else:
        return {"status": "loading"}

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):                         # 普通 def：answer 是慢的同步操作，FastAPI 会放进线程池执行
    """提问：检索 → 生成 → 返回回答和出处"""
    # ① 取出启动时加载好的 retriever
    retriever = app.state.retriever

    # ② 调用 RAG 流程；变量名不能叫 answer，否则会和导入的 answer 函数重名
    try:
        result = answer(req.question, retriever)
    # ③ 两种上游错误：网络重试 3 次仍失败（httpx.HTTPError）、DeepSeek 返回非 200（RuntimeError）
    except (httpx.HTTPError, RuntimeError) as e:
        raise HTTPException(status_code=502, detail=f"大模型调用失败：{e}")   # 立刻结束函数，返回 502

    # ④ 字段名和 AskResponse 一致，FastAPI 自动转换
    return result


