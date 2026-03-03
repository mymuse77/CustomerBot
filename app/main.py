"""FastAPI 应用入口"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.models import ChatRequest, ChatResponse, HealthResponse
from app.text2sql import process_question
from app.database import test_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="视频监控数字人",
    description="基于 Text2SQL + LLM 的视频监控平台智能问答系统",
    version="1.0.0",
)

# 挂载静态文件
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=FileResponse)
async def index():
    """返回前端页面"""
    return FileResponse(str(static_dir / "index.html"))


@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查"""
    db_ok = test_connection()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db_connected=db_ok,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    聊天接口：接收用户自然语言问题，返回数据分析结果。

    流程: 问题 -> Text2SQL -> 执行查询 -> LLM 生成回答
    """
    result = await process_question(req.question)
    return ChatResponse(**result)
