from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path

from database import get_db
from services.file_service import FileService
from models import File as FileModel

router = APIRouter()


@router.post("/upload/chunk")
async def upload_chunk(
    file_id: str = Form(...),
    file_name: str = Form(...),
    file_size: int = Form(...),
    kb_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    chunk: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    return await FileService.upload_chunk(
        db, file_id, file_name, file_size,
        kb_id, chunk_index, total_chunks, chunk.file,
    )


@router.post("/files/{file_id}/process")
async def process_file(
    file_id: str,
    extract_graph: bool = True,
    db: AsyncSession = Depends(get_db),
):
    ok = await FileService.start_processing(file_id, db, extract_graph=extract_graph)
    if not ok:
        raise HTTPException(400, "File not ready for processing")
    return {"status": "processing"}


@router.get("/files/{file_id}/status")
async def file_status(file_id: str, db: AsyncSession = Depends(get_db)):
    result = await FileService.get_status(file_id, db)
    if not result:
        raise HTTPException(404, "File not found")
    return result


@router.get("/files")
async def list_files(db: AsyncSession = Depends(get_db)):
    return await FileService.list_all(db)


@router.delete("/files/{file_id}")
async def delete_file(file_id: str, db: AsyncSession = Depends(get_db)):
    deleted = await FileService.delete(db, file_id)
    if not deleted:
        raise HTTPException(404, "File not found")
    return {"status": "deleted"}


@router.get("/files/{file_id}/preview")
async def preview_file(file_id: str, db: AsyncSession = Depends(get_db)):
    """返回文件内容或文件流，供前端预览。

    TXT/MD: 返回纯文本
    PDF: 返回二进制文件流
    DOCX: 返回 501 未实现
    """
    result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    f = result.scalars().first()
    if not f or not f.path:
        raise HTTPException(404, "File not found")

    fp = Path(f.path)
    if not fp.exists():
        raise HTTPException(404, "File not found on disk")

    ext = fp.suffix.lower()
    if ext in (".txt", ".md"):
        text = fp.read_text(encoding="utf-8", errors="ignore")
        return PlainTextResponse(text)

    if ext == ".pdf":
        return FileResponse(fp, media_type="application/pdf")

    raise HTTPException(501, f"Preview not supported for {ext}")
