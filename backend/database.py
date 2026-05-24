from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from models import Base

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create data directories, tables, and lightweight SQLite migrations."""
    Path("./data").mkdir(exist_ok=True)
    Path(settings.UPLOAD_DIR).mkdir(exist_ok=True)
    (Path(settings.UPLOAD_DIR) / "_assets").mkdir(parents=True, exist_ok=True)
    Path(settings.CHUNK_DIR).mkdir(exist_ok=True)
    Path(settings.KUZU_DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        result = await conn.execute(text("PRAGMA table_info(files)"))
        columns = [row[1] for row in result]
        if "progress" not in columns:
            await conn.execute(text("ALTER TABLE files ADD COLUMN progress INTEGER DEFAULT 0"))
        if "message" not in columns:
            await conn.execute(text("ALTER TABLE files ADD COLUMN message VARCHAR DEFAULT NULL"))
        if "detail" not in columns:
            await conn.execute(text("ALTER TABLE files ADD COLUMN detail TEXT DEFAULT NULL"))
        if "logs" not in columns:
            await conn.execute(text("ALTER TABLE files ADD COLUMN logs TEXT DEFAULT NULL"))
        if "path" not in columns:
            await conn.execute(text("ALTER TABLE files ADD COLUMN path VARCHAR DEFAULT NULL"))
        if "asset_id" not in columns:
            await conn.execute(text("ALTER TABLE files ADD COLUMN asset_id VARCHAR DEFAULT NULL"))


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
