from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid

from sqlalchemy import Column, String, Integer, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    created_at = Column(String, default=lambda: datetime.now().isoformat())

    files = relationship("File", back_populates="kb", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = "files"

    id = Column(String, primary_key=True)
    kb_id = Column(String, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    total_chunks = Column(Integer, nullable=False, default=0)
    status = Column(String, default="uploading")  # uploading / uploaded / processing / indexed / failed
    progress = Column(Integer, default=0)  # 0-100
    path = Column(String, nullable=True)
    created_at = Column(String, default=lambda: datetime.now().isoformat())

    kb = relationship("KnowledgeBase", back_populates="files")
    chunks = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    file_id = Column(String, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding_id = Column(String, nullable=True)  # 向量存储中的 ID
    created_at = Column(String, default=lambda: datetime.now().isoformat())

    file = relationship("File", back_populates="chunks")
