from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import shutil
from time import perf_counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.chunker import split_text
from database import async_session
from models import Chunk, File, KnowledgeBase
from providers.embedding import create_embeddings
from providers.graph_store import (
    ChunkGraphData,
    delete_document_graph,
    get_graph_store_provider_name,
    upsert_document_graph,
)
from providers.parser import get_parser
from providers.vector_store import create_vector_store, get_vector_store_provider_name
from services.graph_extraction_service import GraphExtractionService

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
CHUNK_DIR = Path(settings.CHUNK_DIR)
LOG_TAIL_LIMIT = 120


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FileService:
    @staticmethod
    def _empty_detail() -> dict:
        return {
            "started_at": None,
            "finished_at": None,
            "elapsed_ms": 0,
            "stage": "idle",
            "summary": {
                "chunk_count": 0,
                "entity_count": 0,
                "relation_count": 0,
            },
            "stages": {
                "total": {"progress": 0, "label": "等待开始"},
                "chunking": {"progress": 0, "current": 0, "total": 0, "label": "等待开始"},
                "extraction": {
                    "progress": 0,
                    "processed_batches": 0,
                    "total_batches": 0,
                    "processed_chunks": 0,
                    "total_candidate_chunks": 0,
                    "entity_count": 0,
                    "relation_count": 0,
                    "label": "等待开始",
                },
                "graph": {"progress": 0, "label": "等待开始"},
            },
        }

    @staticmethod
    def _read_detail(file: File) -> dict:
        if not file.detail:
            return FileService._empty_detail()
        try:
            return json.loads(file.detail)
        except Exception:
            return FileService._empty_detail()

    @staticmethod
    def _write_detail(file: File, detail: dict):
        file.detail = json.dumps(detail, ensure_ascii=False)

    @staticmethod
    def _read_logs(file: File) -> list[dict]:
        if not file.logs:
            return []
        try:
            value = json.loads(file.logs)
            return value if isinstance(value, list) else []
        except Exception:
            return []

    @staticmethod
    def _write_logs(file: File, logs: list[dict]):
        file.logs = json.dumps(logs[-LOG_TAIL_LIMIT:], ensure_ascii=False)

    @staticmethod
    def _append_log(file: File, message: str, level: str = "info"):
        logs = FileService._read_logs(file)
        logs.append({
            "time": _utc_now_iso(),
            "level": level,
            "message": message[:500],
        })
        FileService._write_logs(file, logs)

    @staticmethod
    async def _commit_runtime_state(
        db: AsyncSession,
        file: File,
        *,
        progress: int | None = None,
        message: str | None = None,
        stage: str | None = None,
        chunk_progress: dict | None = None,
        extraction_progress: dict | None = None,
        graph_progress: dict | None = None,
        summary: dict | None = None,
        log_message: str | None = None,
        log_level: str = "info",
        status: str | None = None,
        finished: bool = False,
    ):
        detail = FileService._read_detail(file)
        if detail.get("started_at") is None:
            detail["started_at"] = _utc_now_iso()
        if progress is not None:
            file.progress = max(0, min(100, progress))
            detail["stages"]["total"]["progress"] = file.progress
        if message is not None:
            file.message = message[:200]
            detail["stages"]["total"]["label"] = message[:200]
        if stage is not None:
            detail["stage"] = stage
        if chunk_progress:
            detail["stages"]["chunking"].update(chunk_progress)
        if extraction_progress:
            detail["stages"]["extraction"].update(extraction_progress)
        if graph_progress:
            detail["stages"]["graph"].update(graph_progress)
        if summary:
            detail["summary"].update(summary)
        if finished:
            detail["finished_at"] = _utc_now_iso()
        if detail.get("started_at"):
            started = datetime.fromisoformat(detail["started_at"])
            ended = datetime.fromisoformat(detail["finished_at"]) if detail.get("finished_at") else datetime.now(timezone.utc)
            detail["elapsed_ms"] = max(0, int((ended - started).total_seconds() * 1000))
        FileService._write_detail(file, detail)
        if log_message:
            FileService._append_log(file, log_message, log_level)
        if status is not None:
            file.status = status
        await db.commit()

    @staticmethod
    async def upload_chunk(
        db: AsyncSession,
        file_id: str,
        file_name: str,
        file_size: int,
        kb_id: str,
        chunk_index: int,
        total_chunks: int,
        chunk_data,
    ) -> dict:
        file = await db.get(File, file_id)
        if not file:
            file = File(
                id=file_id,
                kb_id=kb_id,
                name=file_name,
                size=file_size,
                total_chunks=total_chunks,
            )
            FileService._write_detail(file, FileService._empty_detail())
            FileService._write_logs(file, [])
            db.add(file)
            await db.commit()

        chunk_path = CHUNK_DIR / f"{file_id}_{chunk_index:06d}"
        with open(chunk_path, "wb") as f:
            shutil.copyfileobj(chunk_data, f)

        received = len(list(CHUNK_DIR.glob(f"{file_id}_*")))
        logger.info(
            "Upload chunk received: file_id=%s kb_id=%s chunk_index=%s/%s received=%s file_name=%s",
            file_id,
            kb_id,
            chunk_index + 1,
            total_chunks,
            received,
            file_name,
        )

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
            file_id,
            file.kb_id,
            len(chunk_files),
            target_path,
        )
        with open(target_path, "wb") as out:
            for chunk_path in chunk_files:
                with open(chunk_path, "rb") as chunk_in:
                    out.write(chunk_in.read())
                chunk_path.unlink()

        file.path = str(target_path)
        await FileService._commit_runtime_state(
            db,
            file,
            status="uploaded",
            progress=0,
            message="上传完成，等待开始处理",
            stage="uploaded",
            log_message="上传完成，文件已重组",
        )
        logger.info(
            "Upload reassembled: file_id=%s kb_id=%s path=%s size=%s",
            file_id,
            file.kb_id,
            file.path,
            file.size,
        )

    @staticmethod
    async def start_processing(file_id: str, db: AsyncSession, extract_graph: bool = True) -> bool:
        file = await db.get(File, file_id)
        if not file or file.status != "uploaded":
            logger.warning(
                "Start processing skipped: file_id=%s status=%s",
                file_id,
                getattr(file, "status", None),
            )
            return False

        detail = FileService._empty_detail()
        detail["started_at"] = _utc_now_iso()
        detail["stage"] = "preparing"
        FileService._write_detail(file, detail)
        FileService._write_logs(file, [])
        await FileService._commit_runtime_state(
            db,
            file,
            status="processing",
            progress=0,
            message="准备开始处理",
            stage="preparing",
            log_message="处理任务已启动",
        )
        logger.info(
            "Start processing: file_id=%s kb_id=%s file_name=%s extract_graph=%s",
            file.id, file.kb_id, file.name, extract_graph,
        )
        asyncio.create_task(FileService._process_file_bg(file_id, extract_graph=extract_graph))
        return True

    @staticmethod
    async def get_status(file_id: str, db: AsyncSession) -> dict | None:
        file = await db.get(File, file_id)
        if not file:
            return None
        return {
            "status": file.status,
            "progress": file.progress,
            "message": file.message,
            "detail": FileService._read_detail(file),
            "logs": FileService._read_logs(file),
        }

    @staticmethod
    async def _process_file_bg(file_id: str, extract_graph: bool = True):
        async with async_session() as db:
            try:
                file = await db.get(File, file_id)
                if not file or not file.path:
                    logger.warning("Background processing aborted: file_id=%s missing file or path", file_id)
                    return

                kb = await db.get(KnowledgeBase, file.kb_id)
                if not kb:
                    raise ValueError(f"Knowledge base not found: {file.kb_id}")

                file_path = Path(file.path)
                vector_provider_name = get_vector_store_provider_name()
                graph_provider_name = get_graph_store_provider_name()
                pipeline_started = perf_counter()

                logger.info(
                    "Processing pipeline started: file_id=%s kb_id=%s file_name=%s vector_provider=%s graph_provider=%s path=%s",
                    file.id,
                    file.kb_id,
                    file.name,
                    vector_provider_name,
                    graph_provider_name,
                    file.path,
                )
                await FileService._commit_runtime_state(
                    db,
                    file,
                    progress=5,
                    message="正在解析文档",
                    stage="parsing",
                    chunk_progress={"label": "等待分片", "progress": 0, "current": 0, "total": 0},
                    extraction_progress={"label": "等待抽取", "progress": 0},
                    graph_progress={"label": "等待写图", "progress": 0},
                    log_message="开始解析文档",
                )

                parse_started = perf_counter()
                parser = get_parser(file_path)
                result = parser.parse(file_path)
                parse_ms = (perf_counter() - parse_started) * 1000
                logger.info(
                    "Parsing completed: file_id=%s content_chars=%s metadata_keys=%s duration_ms=%.0f",
                    file.id,
                    len(result.content or ""),
                    sorted((result.metadata or {}).keys()),
                    parse_ms,
                )
                await FileService._commit_runtime_state(
                    db,
                    file,
                    progress=15,
                    message="正在切分文本",
                    stage="chunking",
                    log_message=f"文档解析完成，用时 {parse_ms / 1000:.1f}s",
                )

                chunk_started = perf_counter()
                text_chunks = split_text(result.content, result.metadata)
                if not text_chunks:
                    await FileService._commit_runtime_state(
                        db,
                        file,
                        status="failed",
                        progress=file.progress,
                        message="文档内容为空，暂不支持扫描图片类 PDF 的文本抽取。",
                        stage="failed",
                        log_message="文档分片失败：解析结果为空",
                        log_level="error",
                        finished=True,
                    )
                    logger.warning("Document content empty after parsing: file_id=%s", file_id)
                    return

                from langchain_core.documents import Document

                docs = [
                    Document(
                        page_content=chunk["content"],
                        metadata={
                            "file_id": file_id,
                            "file_name": file.name,
                            "chunk_index": chunk["index"],
                            "start_offset": chunk["start_offset"],
                            "end_offset": chunk["end_offset"],
                            "page_number": chunk.get("page_number"),
                            "file_ext": file_path.suffix.lower(),
                        },
                    )
                    for chunk in text_chunks
                ]
                chunk_ms = (perf_counter() - chunk_started) * 1000
                await FileService._commit_runtime_state(
                    db,
                    file,
                    progress=25,
                    message=f"分片完成，共 {len(docs)} 个分片",
                    stage="chunked",
                    chunk_progress={
                        "progress": 100,
                        "current": len(docs),
                        "total": len(docs),
                        "label": f"已切分 {len(docs)} / {len(docs)}",
                    },
                    summary={"chunk_count": len(docs)},
                    log_message=f"文本切分完成：{len(docs)} 个分片，用时 {chunk_ms / 1000:.1f}s",
                )

                embeddings = create_embeddings()
                vectorstore = create_vector_store(file.kb_id, embeddings)
                chunk_ids = [f"{file_id}_{index}" for index in range(len(docs))]
                await FileService._commit_runtime_state(
                    db,
                    file,
                    progress=35,
                    message=f"正在生成向量，共 {len(docs)} 个分片",
                    stage="vectorizing",
                    log_message=f"开始写入向量库，provider={vector_provider_name}",
                )
                vector_started = perf_counter()
                await asyncio.to_thread(vectorstore.add_documents, docs, ids=chunk_ids)
                vector_ms = (perf_counter() - vector_started) * 1000
                logger.info(
                    "Vector write completed: file_id=%s kb_id=%s provider=%s count=%s duration_ms=%.0f",
                    file.id,
                    file.kb_id,
                    vector_provider_name,
                    len(chunk_ids),
                    vector_ms,
                )
                await FileService._commit_runtime_state(
                    db,
                    file,
                    progress=55,
                    message="向量写入完成，准备抽取实体与关系",
                    stage="extract_prepare",
                    log_message=f"向量写入完成，用时 {vector_ms / 1000:.1f}s",
                )

                graph_chunks = [
                    ChunkGraphData(
                        chunk_id=chunk_ids[index],
                        chunk_index=text_chunks[index]["index"],
                        content=text_chunks[index]["content"],
                    )
                    for index in range(len(text_chunks))
                ]

                entity_count = 0
                relation_count = 0

                if extract_graph:
                    # Set up KB + Document metadata and clear old graph data first
                    await asyncio.to_thread(
                        upsert_document_graph,
                        file.kb_id,
                        kb.name,
                        file.id,
                        file.name,
                        file.path or "",
                        [],
                        True,  # clear_existing
                    )
                    extraction_started = perf_counter()
                    last_ui_update = {"batch": 0, "ts": perf_counter()}
                    last_log_flush = {"ts": 0.0}
                    accumulated_entity_count = {"value": 0}
                    accumulated_relation_count = {"value": 0}

                    async def batch_result_callback(batch_chunks: list):
                        await asyncio.to_thread(
                            upsert_document_graph,
                            file.kb_id,
                            kb.name,
                            file.id,
                            file.name,
                            file.path or "",
                            batch_chunks,
                            False,  # clear_existing=False, incremental write
                        )
                        accumulated_entity_count["value"] += sum(
                            len(chunk.entities) for chunk in batch_chunks
                        )
                        accumulated_relation_count["value"] += sum(
                            len(chunk.relations) for chunk in batch_chunks
                        )
                        await FileService._commit_runtime_state(
                            db,
                            file,
                            extraction_progress={
                                "entity_count": accumulated_entity_count["value"],
                                "relation_count": accumulated_relation_count["value"],
                            },
                        )

                    async def extraction_progress_callback(
                        processed_batches: int,
                        total_batches: int,
                        processed_chunks: int,
                        total_candidate_chunks: int,
                    ):
                        ratio = processed_batches / max(total_batches, 1)
                        progress = 56 + int(ratio * 24)
                        now = perf_counter()
                        if (
                            processed_batches != total_batches
                            and processed_batches != 1
                            and now - last_ui_update["ts"] < 0.5
                        ):
                            return
                        last_ui_update["batch"] = processed_batches
                        last_ui_update["ts"] = now
                        await FileService._commit_runtime_state(
                            db,
                            file,
                            progress=progress,
                            message=f"正在抽取实体与关系：批次 {processed_batches}/{total_batches}",
                            stage="extracting",
                            extraction_progress={
                                "progress": int(ratio * 100),
                                "processed_batches": processed_batches,
                                "total_batches": total_batches,
                                "processed_chunks": processed_chunks,
                                "total_candidate_chunks": total_candidate_chunks,
                                "entity_count": accumulated_entity_count["value"],
                                "relation_count": accumulated_relation_count["value"],
                                "label": f"已完成批次 {processed_batches}/{total_batches}",
                            },
                        )

                    async def extraction_log_callback(message: str):
                        now = perf_counter()
                        should_flush = (
                            "开始请求大模型抽取" in message
                            or "抽取完成" in message
                            or "抽取失败" in message
                            or "阶段完成" in message
                            or (now - last_log_flush["ts"]) >= 0.5
                        )
                        if not should_flush:
                            return
                        last_log_flush["ts"] = now
                        await FileService._commit_runtime_state(
                            db,
                            file,
                            log_message=message,
                            message=file.message,
                        )

                    graph_chunks = await GraphExtractionService.extract(
                        file.name,
                        graph_chunks,
                        progress_callback=extraction_progress_callback,
                        log_callback=extraction_log_callback,
                        batch_result_callback=batch_result_callback,
                    )
                    entity_count = sum(len(chunk.entities) for chunk in graph_chunks)
                    relation_count = sum(len(chunk.relations) for chunk in graph_chunks)
                    extraction_ms = (perf_counter() - extraction_started) * 1000
                    logger.info(
                        "Graph extraction completed: file_id=%s kb_id=%s chunks=%s entities=%s relations=%s duration_ms=%.0f",
                        file.id,
                        file.kb_id,
                        len(graph_chunks),
                        entity_count,
                        relation_count,
                        extraction_ms,
                    )
                    await FileService._commit_runtime_state(
                        db,
                        file,
                        progress=82,
                        message=f"抽取完成：实体 {entity_count}，关系 {relation_count}",
                        stage="graph_writing",
                        extraction_progress={
                            "progress": 100,
                            "entity_count": entity_count,
                            "relation_count": relation_count,
                            "label": f"已抽取实体 {entity_count}，关系 {relation_count}",
                        },
                        summary={"entity_count": entity_count, "relation_count": relation_count},
                        graph_progress={"progress": 15, "label": "准备写入图谱"},
                        log_message=f"实体与关系抽取完成，用时 {extraction_ms / 1000:.1f}s",
                    )

                    graph_write_started = perf_counter()
                    await FileService._commit_runtime_state(
                        db,
                        file,
                        progress=86,
                        message="正在写入图谱",
                        stage="graph_writing",
                        graph_progress={"progress": 40, "label": f"正在写入图数据库（{graph_provider_name}）"},
                        log_message=f"开始写入图谱，provider={graph_provider_name}",
                    )
                    await asyncio.to_thread(
                        upsert_document_graph,
                        file.kb_id,
                        kb.name,
                        file.id,
                        file.name,
                        file.path or "",
                        graph_chunks,
                        False,  # clear_existing=False, incremental data already written
                    )
                    graph_ms = (perf_counter() - graph_write_started) * 1000
                    logger.info(
                        "Graph write completed: file_id=%s kb_id=%s provider=%s chunks=%s duration_ms=%.0f",
                        file.id,
                        file.kb_id,
                        graph_provider_name,
                        len(graph_chunks),
                        graph_ms,
                    )
                    await FileService._commit_runtime_state(
                        db,
                        file,
                        progress=92,
                        message="图谱写入完成，正在保存分片记录",
                        stage="saving",
                        graph_progress={"progress": 100, "label": "图谱写入完成"},
                        log_message=f"图谱写入完成，用时 {graph_ms / 1000:.1f}s",
                    )
                else:
                    await FileService._commit_runtime_state(
                        db,
                        file,
                        progress=75,
                        message="已跳过图谱抽取，正在保存分片记录",
                        stage="saving",
                        extraction_progress={"progress": 100, "label": "已跳过图谱抽取"},
                        graph_progress={"progress": 100, "label": "已跳过"},
                        summary={"entity_count": 0, "relation_count": 0},
                        log_message="已跳过实体与关系抽取（extract_graph=false）",
                    )

                sql_started = perf_counter()
                for index, chunk in enumerate(text_chunks):
                    db.add(
                        Chunk(
                            id=chunk_ids[index],
                            file_id=file_id,
                            content=chunk["content"],
                            chunk_index=chunk["index"],
                            embedding_id=chunk_ids[index],
                        )
                    )

                total_ms = (perf_counter() - pipeline_started) * 1000
                await FileService._commit_runtime_state(
                    db,
                    file,
                    status="indexed",
                    progress=100,
                    message=(
                        f"处理完成：{len(text_chunks)} 个分片，"
                        f"{entity_count} 个实体，{relation_count} 个关系"
                    ),
                    stage="completed",
                    graph_progress={"progress": 100, "label": "分片记录已保存"},
                    summary={
                        "chunk_count": len(text_chunks),
                        "entity_count": entity_count,
                        "relation_count": relation_count,
                    },
                    log_message=(
                        f"处理完成，总耗时 {total_ms / 1000:.1f}s，"
                        f"分片 {len(text_chunks)}，实体 {entity_count}，关系 {relation_count}"
                    ),
                    finished=True,
                )
                logger.info(
                    "Chunk row persistence completed: file_id=%s kb_id=%s count=%s duration_ms=%.0f",
                    file.id,
                    file.kb_id,
                    len(text_chunks),
                    (perf_counter() - sql_started) * 1000,
                )
                logger.info(
                    "Processing pipeline finished: file_id=%s kb_id=%s status=%s progress=%s total_duration_ms=%.0f",
                    file.id,
                    file.kb_id,
                    file.status,
                    file.progress,
                    total_ms,
                )
            except Exception as exc:
                logger.exception("Processing pipeline failed: file_id=%s error=%s", file_id, exc)
                try:
                    file = await db.get(File, file_id)
                    if file:
                        await FileService._commit_runtime_state(
                            db,
                            file,
                            status="failed",
                            message=str(exc)[:200],
                            stage="failed",
                            log_message=f"处理失败：{exc}",
                            log_level="error",
                            finished=True,
                        )
                except Exception:
                    pass

    @staticmethod
    async def list_all(db: AsyncSession) -> list[dict]:
        result = await db.execute(select(File))
        files = result.scalars().all()
        return [
            {
                "id": file.id,
                "name": file.name,
                "size": file.size,
                "kb_id": file.kb_id,
                "status": file.status,
                "progress": file.progress,
                "message": file.message,
                "detail": FileService._read_detail(file),
                "logs": FileService._read_logs(file),
            }
            for file in files
        ]

    @staticmethod
    async def delete(db: AsyncSession, file_id: str) -> bool:
        file = await db.get(File, file_id)
        if not file:
            logger.warning("Delete file skipped: file_id=%s not found", file_id)
            return False

        embeddings = create_embeddings()
        chunks = (await db.execute(select(Chunk).where(Chunk.file_id == file_id))).scalars().all()
        vector_provider_name = get_vector_store_provider_name()
        graph_provider_name = get_graph_store_provider_name()
        logger.info(
            "Deleting file assets: file_id=%s kb_id=%s chunk_rows=%s vector_provider=%s graph_provider=%s",
            file.id,
            file.kb_id,
            len(chunks),
            vector_provider_name,
            graph_provider_name,
        )

        if chunks:
            try:
                vectorstore = create_vector_store(file.kb_id, embeddings)
                ids_to_delete = [chunk.embedding_id for chunk in chunks if chunk.embedding_id]
                await asyncio.to_thread(vectorstore.delete, ids=ids_to_delete)
            except Exception:
                logger.exception("Vector delete failed: file_id=%s kb_id=%s", file.id, file.kb_id)

        try:
            await asyncio.to_thread(delete_document_graph, file.id)
        except Exception:
            logger.exception("Graph delete failed: file_id=%s kb_id=%s", file.id, file.kb_id)

        if file.path:
            file_path = Path(file.path)
            if file_path.exists():
                file_path.unlink()

        for chunk_path in CHUNK_DIR.glob(f"{file_id}_*"):
            chunk_path.unlink()

        await db.delete(file)
        await db.commit()
        logger.info("File delete completed: file_id=%s kb_id=%s", file.id, file.kb_id)
        return True
