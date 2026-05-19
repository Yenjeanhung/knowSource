from pydantic import BaseModel
from typing import Optional


class CreateKBRequest(BaseModel):
    name: str


class UpdateKBRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class QueryRequest(BaseModel):
    query: str
    kb_id: str
    top_k: int = 5
