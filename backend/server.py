"""
KnowSource Backend — 基于知识库的 RAG 问答服务。

启动: pip install -r requirements.txt && python server.py
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库和 Provider 单例。"""
    logger.info("正在初始化数据库...")
    await init_db()

    logger.info("正在加载嵌入模型...")
    from providers.embedding import create_embeddings
    create_embeddings()  # 预加载，后续直接用缓存

    logger.info("正在加载 LLM...")
    from providers.llm import create_llm
    create_llm()  # 预加载

    logger.info("KnowSource 服务已启动")
    yield
    logger.info("KnowSource 服务已关闭")


app = FastAPI(title="KnowSource", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from routers import kb, files, query
app.include_router(kb.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(query.router, prefix="/api")

# 生产环境：托管前端静态文件
front_dist = Path(__file__).parent.parent / "front" / "dist"
if front_dist.exists():
    app.mount("/", StaticFiles(directory=str(front_dist), html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
