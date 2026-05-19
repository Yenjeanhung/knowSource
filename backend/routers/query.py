from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import QueryRequest
from services.rag_service import RAGService
from services.kb_service import KBService

router = APIRouter()


@router.post("/query")
async def query_rag(req: QueryRequest, db: AsyncSession = Depends(get_db)):
    kb = await KBService.get(db, req.kb_id)
    if not kb:
        raise HTTPException(404, "Knowledge base not found")
    return await RAGService.query(db, req.kb_id, req.query, req.top_k)
