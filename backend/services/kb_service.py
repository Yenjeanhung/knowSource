import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import KnowledgeBase
from config import settings


class KBService:

    @staticmethod
    async def create(db: AsyncSession, name: str) -> dict:
        kb = KnowledgeBase(name=name.strip())
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        return {"id": kb.id, "name": kb.name, "created_at": kb.created_at, "files": {}}

    @staticmethod
    async def list_all(db: AsyncSession) -> list[dict]:
        result = await db.execute(
            select(KnowledgeBase).options(selectinload(KnowledgeBase.files))
        )
        kbs = result.scalars().all()
        return [
            {"id": kb.id, "name": kb.name, "created_at": kb.created_at,
             "file_count": len(kb.files)}
            for kb in kbs
        ]

    @staticmethod
    async def get(db: AsyncSession, kb_id: str) -> dict | None:
        result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = result.scalar_one_or_none()
        if not kb:
            return None
        files = [
            {"id": f.id, "name": f.name, "size": f.size, "status": f.status}
            for f in kb.files
        ]
        return {
            "id": kb.id, "name": kb.name, "created_at": kb.created_at,
            "file_count": len(kb.files), "files": files,
        }

    @staticmethod
    async def delete(db: AsyncSession, kb_id: str) -> bool:
        result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        kb = result.scalar_one_or_none()
        if not kb:
            return False

        # 删除文件目录
        kb_dir = Path(settings.UPLOAD_DIR) / kb_id
        if kb_dir.exists():
            shutil.rmtree(kb_dir)

        # 删除向量 Collection
        from providers.vector_store import delete_kb_collection
        delete_kb_collection(kb_id)

        # 删除数据库记录（级联删除 files 和 chunks）
        await db.delete(kb)
        await db.commit()
        return True
