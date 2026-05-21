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
from providers.vector_store import create_vector_store, get_vector_store_provider_name
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
        logger.info(
            "Upload chunk received: file_id=%s kb_id=%s chunk_index=%s/%s received=%s file_name=%s",
            file_id, kb_id, chunk_index + 1, total_chunks, received, file_name,
        )

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
        logger.info(
            "Reassembling upload: file_id=%s kb_id=%s chunks=%s target=%s",
            file_id, file.kb_id, len(chunk_files), target_path,
        )
        with open(target_path, "wb") as out:
            for cp in chunk_files:
                with open(cp, "rb") as cin:
                    out.write(cin.read())
                cp.unlink()

        file.path = str(target_path)
        file.status = "uploaded"
        await db.commit()
        logger.info(
            "Upload reassembled: file_id=%s kb_id=%s path=%s size=%s",
            file_id, file.kb_id, file.path, file.size,
        )

    @staticmethod
    async def start_processing(file_id: str, db: AsyncSession) -> bool:
        file = await db.get(File, file_id)
        if not file or file.status != "uploaded":
            logger.warning("Start processing skipped: file_id=%s status=%s", file_id, getattr(file, "status", None))
            return False
        file.status = "processing"
        file.progress = 0
        await db.commit()
        logger.info("Start processing: file_id=%s kb_id=%s file_name=%s", file.id, file.kb_id, file.name)
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
                    logger.warning("Background processing aborted: file_id=%s missing file or path", file_id)
                    return

                file_path = Path(file.path)
                provider_name = get_vector_store_provider_name()
                logger.info(
                    "Processing pipeline started: file_id=%s kb_id=%s file_name=%s provider=%s path=%s",
                    file.id, file.kb_id, file.name, provider_name, file.path,
                )

                # 1. 解析文档
                file.progress = 10
                await db.commit()

                parser = get_parser(file_path)
                logger.info(
                    "Parsing file: file_id=%s parser=%s suffix=%s",
                    file.id, parser.__class__.__name__, file_path.suffix.lower(),
                )
                result = parser.parse(file_path)
                logger.info(
                    "Parsing completed: file_id=%s content_chars=%s metadata_keys=%s",
                    file.id, len(result.content or ""), sorted((result.metadata or {}).keys()),
                )

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
                logger.info(
                    "Chunking completed: file_id=%s kb_id=%s chunk_count=%s first_chunk_len=%s",
                    file.id, file.kb_id, total, len(text_chunks[0]["content"]) if text_chunks else 0,
                )

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
                logger.info(
                    "LangChain documents prepared: file_id=%s doc_count=%s",
                    file.id, len(docs),
                )

                # 4. 写入向量库
                file.progress = 40
                await db.commit()

                embeddings = create_embeddings()
                vectorstore = create_vector_store(file.kb_id, embeddings)
                chunk_ids = [f"{file_id}_{i}" for i in range(len(docs))]
                logger.info(
                    "Writing vectors: file_id=%s kb_id=%s provider=%s collection=%s ids=%s..%s count=%s",
                    file.id,
                    file.kb_id,
                    provider_name,
                    file.kb_id,
                    chunk_ids[0] if chunk_ids else None,
                    chunk_ids[-1] if chunk_ids else None,
                    len(chunk_ids),
                )
                await asyncio.to_thread(
                    vectorstore.add_documents, docs, ids=chunk_ids
                )
                logger.info(
                    "Vector write completed: file_id=%s kb_id=%s provider=%s count=%s",
                    file.id, file.kb_id, provider_name, len(chunk_ids),
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
                logger.info(
                    "Persisting chunk rows: file_id=%s kb_id=%s row_count=%s",
                    file.id, file.kb_id, len(text_chunks),
                )

                file.status = "indexed"
                file.progress = 100
                await db.commit()
                logger.info(
                    "Processing pipeline finished: file_id=%s kb_id=%s status=%s progress=%s",
                    file.id, file.kb_id, file.status, file.progress,
                )

            except Exception as e:
                logger.exception("Processing pipeline failed: file_id=%s error=%s", file_id, e)
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
            logger.warning("Delete file skipped: file_id=%s not found", file_id)
            return False

        embeddings = create_embeddings()
        chunks = (await db.execute(
            select(Chunk).where(Chunk.file_id == file_id)
        )).scalars().all()
        provider_name = get_vector_store_provider_name()
        logger.info(
            "Deleting file and vectors: file_id=%s kb_id=%s chunk_rows=%s provider=%s",
            file.id, file.kb_id, len(chunks), provider_name,
        )

        if chunks:
            try:
                vs = create_vector_store(file.kb_id, embeddings)
                ids_to_delete = [c.embedding_id for c in chunks if c.embedding_id]
                logger.info(
                    "Deleting vectors from store: file_id=%s kb_id=%s provider=%s count=%s",
                    file.id, file.kb_id, provider_name, len(ids_to_delete),
                )
                await asyncio.to_thread(
                    vs.delete, ids=ids_to_delete
                )
                logger.info(
                    "Vector delete completed: file_id=%s kb_id=%s provider=%s",
                    file.id, file.kb_id, provider_name,
                )
            except Exception:
                logger.exception("Vector delete failed: file_id=%s kb_id=%s provider=%s", file.id, file.kb_id, provider_name)

        if file.path:
            fp = Path(file.path)
            if fp.exists():
                fp.unlink()

        for cp in CHUNK_DIR.glob(f"{file_id}_*"):
            cp.unlink()

        await db.delete(file)
        await db.commit()
        logger.info("File delete completed: file_id=%s kb_id=%s", file.id, file.kb_id)
        return True
