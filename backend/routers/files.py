from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.file_service import FileService

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
async def process_file(file_id: str, db: AsyncSession = Depends(get_db)):
    ok = await FileService.start_processing(file_id, db)
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
