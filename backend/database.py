from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config import settings
from models import Base
from sqlalchemy import text

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """创建数据目录和数据库表。"""
    Path("./data").mkdir(exist_ok=True)
    Path(settings.UPLOAD_DIR).mkdir(exist_ok=True)
    Path(settings.CHUNK_DIR).mkdir(exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 迁移：给已有 files 表加 progress 列
        result = await conn.execute(text("PRAGMA table_info(files)"))
        columns = [row[1] for row in result]
        if "progress" not in columns:
            await conn.execute(text("ALTER TABLE files ADD COLUMN progress INTEGER DEFAULT 0"))


async def get_db() -> AsyncSession:
    """FastAPI 依赖：获取数据库会话。"""
    async with async_session() as session:
        yield session
