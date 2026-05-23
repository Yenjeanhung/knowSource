"""
KnowSource backend entrypoint.
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
    """Initialize storage and provider singletons at startup."""
    logger.info("Initializing database...")
    await init_db()

    logger.info("Loading embedding provider...")
    from providers.embedding import create_embeddings

    create_embeddings()

    logger.info("Loading LLM provider...")
    from providers.llm import create_llm

    create_llm()

    logger.info("Ensuring graph store schema...")
    from providers.graph_store import ensure_graph_schema

    ensure_graph_schema()

    logger.info("Cleaning up zombie processing tasks...")
    from services.file_service import FileService
    from database import get_db

    async for db in get_db():
        await FileService.cleanup_zombie_tasks(db)

    logger.info("KnowSource started.")
    yield
    logger.info("KnowSource stopped.")


app = FastAPI(title="KnowSource", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers import files, graph, kb, query, vector_data

app.include_router(kb.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(vector_data.router, prefix="/api")

front_dist = Path(__file__).parent.parent / "front" / "dist"
if front_dist.exists():
    app.mount("/", StaticFiles(directory=str(front_dist), html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
