import asyncio
from fastapi.responses import StreamingResponse
from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from week3.models import ChatRequest
import json

app = FastAPI()

class Message(BaseModel):
    role: str
    content: str

class Receive(BaseModel):
    role: str
    content: str

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.get("/users/{user_id}")
def read_user(user_id: int):
    if user_id != 123:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"user_id": user_id}

@app.get("/search")
def search_user(keyword:str, limit:int):
    return {"keyword":keyword,"limit":limit}

@app.post("/chat")
def chat(req: ChatRequest):
    return {
        "message_count": len(req.messages),
        "last_message": req.messages[-1].content,
        "model": req.model,
        "temperature": req.temperature,
    }

async def generate_text():
    """异步生成器：逐字产出 SSE 数据块"""
    text = "你好，我是一个AI助手，很高兴为你服务。"
    for char in text:
        yield f"data: {char}\n\n"
        # yield 一次 = 发出一块
        # 注意末尾是两个 \n，这是 SSE 的消息分隔符，少一个客户端会一直等
        await asyncio.sleep(0.5)
        # 模拟生成延迟。必须用 asyncio.sleep，不能用 time.sleep
    yield "data: [DONE]\n\n"
    # 结束标志

async def generate_json_text(content):
    reply = f"收到你的问题：{content}，我正在思考"
    prompt_tokens = len(content)
    completion_tokens = 0
    for char in reply:
        completion_tokens = completion_tokens + 1
        data={"type":"delta","content":char}
        text = json.dumps(data, ensure_ascii=False)
        yield f"data: {text}\n\n"
        await asyncio.sleep(0.5)
    total_tokens = completion_tokens + prompt_tokens
    zd={"type":"usage",
        "prompt_tokens":prompt_tokens,
        "completion_tokens":completion_tokens,
        "total_tokens":total_tokens}
    zd_json=json.dumps(zd,ensure_ascii=False)
    yield f"data: {zd_json}\n\n"
    yield "data: [DONE]\n\n"

@app.get("/stream")
async def stream():
    return StreamingResponse(
        generate_text(),
        media_type="text/event-stream",
    )
    # StreamingResponse 告诉 FastAPI：别等函数跑完，边产出边发
    # media_type 告诉客户端：这是 SSE 流

@app.post("/chat/stream")
async def chat_stream(receive: Receive):
    return StreamingResponse(
        generate_json_text(receive.content),
        media_type="text/event-stream",
    )