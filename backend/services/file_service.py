import asyncio
import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import File, Chunk
from config import settings
from database import async_session
from providers.embedding import create_embeddings
from providers.vector_store import create_vector_store
from providers.parser import get_parser
from core.chunker import split_text

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
CHUNK_DIR = Path(settings.CHUNK_DIR)


class FileService:

    @staticmethod
    async def upload_chunk(
        db: AsyncSession,
        file_id: str, file_name: str, file_size: int,
        kb_id: str, chunk_index: int, total_chunks: int,
        chunk_data,
    ) -> dict:
        file = await db.get(File, file_id)
        if not file:
            file = File(
                id=file_id, kb_id=kb_id, name=file_name,
                size=file_size, total_chunks=total_chunks,
            )
            db.add(file)
            await db.commit()

        chunk_path = CHUNK_DIR / f"{file_id}_{chunk_index:06d}"
        with open(chunk_path, "wb") as f:
            shutil.copyfileobj(chunk_data, f)

        received = len(list(CHUNK_DIR.glob(f"{file_id}_*")))

        # 全部分片到达 → 合并，但不自动处理，等用户确认
        if received == total_chunks:
            await FileService._reassemble(file_id, file, db)

        return {"status": "ok", "chunk_index": chunk_index, "received": received}

    @staticmethod
    async def _reassemble(file_id: str, file: File, db: AsyncSession):
        kb_dir = UPLOAD_DIR / file.kb_id
        kb_dir.mkdir(exist_ok=True)
        target_path = kb_dir / file.name

        chunk_files = sorted(CHUNK_DIR.glob(f"{file_id}_*"))
        with open(target_path, "wb") as out:
            for cp in chunk_files:
                with open(cp, "rb") as cin:
                    out.write(cin.read())
                cp.unlink()

        file.path = str(target_path)
        file.status = "uploaded"
        await db.commit()

    @staticmethod
    async def start_processing(file_id: str, db: AsyncSession) -> bool:
        file = await db.get(File, file_id)
        if not file or file.status != "uploaded":
            return False
        file.status = "processing"
        file.progress = 0
        await db.commit()
        asyncio.create_task(FileService._process_file_bg(file_id))
        return True

    @staticmethod
    async def get_status(file_id: str, db: AsyncSession) -> dict | None:
        file = await db.get(File, file_id)
        if not file:
            return None
        return {"status": file.status, "progress": file.progress, "message": file.message}

    @staticmethod
    async def _process_file_bg(file_id: str):
        async with async_session() as db:
            try:
                file = await db.get(File, file_id)
                if not file or not file.path:
                    return

                file_path = Path(file.path)

                # 1. 解析文档
                file.progress = 10
                await db.commit()

                parser = get_parser(file_path)
                result = parser.parse(file_path)

                # 2. 文本分块
                file.progress = 25
                await db.commit()

                text_chunks = split_text(result.content, result.metadata)
                if not text_chunks:
                    file.status = "failed"
                    file.message = "文档内容为空，可能为扫描版 PDF（不支持图片/扫描格式）"
                    await db.commit()
                    logger.warning(f"文件 {file_id} 解析内容为空，可能为扫描版 PDF")
                    return

                total = len(text_chunks)

                # 3. 构建 LangChain Documents
                from langchain_core.documents import Document
                docs = [
                    Document(
                        page_content=c["content"],
                        metadata={
                            "file_id": file_id,
                            "file_name": file.name,
                            "chunk_index": c["index"],
                            "start_offset": c["start_offset"],
                            "end_offset": c["end_offset"],
                            "page_number": c.get("page_number"),
                            "file_ext": file_path.suffix.lower(),
                        },
                    )
                    for c in text_chunks
                ]

                # 4. 写入向量库
                file.progress = 40
                await db.commit()

                embeddings = create_embeddings()
                vectorstore = create_vector_store(file.kb_id, embeddings)
                chunk_ids = [f"{file_id}_{i}" for i in range(len(docs))]
                await asyncio.to_thread(
                    vectorstore.add_documents, docs, ids=chunk_ids
                )

                file.progress = 85
                await db.commit()

                # 5. 保存分块记录到 SQLite
                for i, chunk in enumerate(text_chunks):
                    db_chunk = Chunk(
                        id=chunk_ids[i],
                        file_id=file_id,
                        content=chunk["content"],
                        chunk_index=chunk["index"],
                        embedding_id=chunk_ids[i],
                    )
                    db.add(db_chunk)

                file.status = "indexed"
                file.progress = 100
                await db.commit()

            except Exception as e:
                logger.error(f"处理文件失败 {file_id}: {e}")
                try:
                    file = await db.get(File, file_id)
                    if file:
                        file.status = "failed"
                        file.message = str(e)[:200]
                        await db.commit()
                except Exception:
                    pass

    @staticmethod
    async def list_all(db: AsyncSession) -> list[dict]:
        result = await db.execute(select(File))
        files = result.scalars().all()
        return [
            {"id": f.id, "name": f.name, "size": f.size,
             "kb_id": f.kb_id, "status": f.status, "progress": f.progress,
             "message": f.message}
            for f in files
        ]

    @staticmethod
    async def delete(db: AsyncSession, file_id: str) -> bool:
        file = await db.get(File, file_id)
        if not file:
            return False

        embeddings = create_embeddings()
        chunks = (await db.execute(
            select(Chunk).where(Chunk.file_id == file_id)
        )).scalars().all()

        if chunks:
            try:
                vs = create_vector_store(file.kb_id, embeddings)
                await asyncio.to_thread(
                    vs.delete, ids=[c.embedding_id for c in chunks if c.embedding_id]
                )
            except Exception:
                pass

        if file.path:
            fp = Path(file.path)
            if fp.exists():
                fp.unlink()

        for cp in CHUNK_DIR.glob(f"{file_id}_*"):
            cp.unlink()

        await db.delete(file)
        await db.commit()
        return True
