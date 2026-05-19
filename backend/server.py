"""
MiniRAG Backend — simple chunked upload + RAG retrieval server.
Run: pip install fastapi uvicorn && python server.py
"""
import os
import json
import hashlib
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="MiniRAG")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
CHUNK_DIR = Path(__file__).parent / "chunks"
UPLOAD_DIR.mkdir(exist_ok=True)
CHUNK_DIR.mkdir(exist_ok=True)

# In-memory registry (use a DB in production)
file_registry: dict[str, dict] = {}  # file_id -> {name, size, chunks, chunk_count}


class QueryRequest(BaseModel):
    query: str
    file_ids: Optional[list[str]] = None
    top_k: int = 5


# ─── File chunk upload ───────────────────────────────────────────────

@app.post("/api/upload/chunk")
async def upload_chunk(
    file_id: str = Form(...),
    file_name: str = Form(...),
    file_size: int = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    chunk: UploadFile = File(...),
):
    # Register file on first chunk
    if file_id not in file_registry:
        file_registry[file_id] = {
            "name": file_name,
            "size": file_size,
            "chunks": [],
            "total_chunks": total_chunks,
        }

    # Save chunk
    chunk_path = CHUNK_DIR / f"{file_id}_{chunk_index:06d}"
    with open(chunk_path, "wb") as f:
        shutil.copyfileobj(chunk.file, f)

    file_registry[file_id]["chunks"].append(chunk_index)

    # If all chunks received, reassemble
    if len(file_registry[file_id]["chunks"]) == total_chunks:
        reassemble_file(file_id)

    return {"status": "ok", "chunk_index": chunk_index, "received": len(file_registry[file_id]["chunks"])}


def reassemble_file(file_id: str):
    info = file_registry[file_id]
    target_path = UPLOAD_DIR / info["name"]
    chunks = sorted(info["chunks"])

    with open(target_path, "wb") as out:
        for idx in chunks:
            chunk_path = CHUNK_DIR / f"{file_id}_{idx:06d}"
            with open(chunk_path, "rb") as cin:
                out.write(cin.read())
            chunk_path.unlink()  # clean up chunk

    info["status"] = "done"
    info["path"] = str(target_path)


# ─── File management ─────────────────────────────────────────────────

@app.get("/api/files")
async def list_files():
    return [
        {
            "id": fid,
            "name": info["name"],
            "size": info["size"],
            "status": info.get("status", "uploading"),
        }
        for fid, info in file_registry.items()
    ]


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    if file_id not in file_registry:
        raise HTTPException(404, "File not found")
    info = file_registry.pop(file_id)
    # Remove assembled file if exists
    fp = Path(info.get("path", ""))
    if fp.exists():
        fp.unlink()
    # Remove any leftover chunks
    for cf in CHUNK_DIR.glob(f"{file_id}_*"):
        cf.unlink()
    return {"status": "deleted"}


# ─── Simple RAG query (keyword-based demo) ───────────────────────────

@app.post("/api/query")
async def query_rag(req: QueryRequest):
    results = []
    for fid, info in file_registry.items():
        if info.get("status") != "done":
            continue
        if req.file_ids and fid not in req.file_ids:
            continue

        fp = Path(info.get("path", ""))
        if not fp.exists():
            continue

        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue

        # Simple keyword match — replace with embedding + vector search
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        for p in paragraphs:
            score = keyword_score(req.query.lower(), p.lower())
            if score > 0:
                results.append({
                    "file_id": fid,
                    "file_name": info["name"],
                    "text": p[:500],
                    "score": min(score, 0.99),
                })

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[: req.top_k]

    answer = synthesize_answer(req.query, top) if top else "No relevant content found in uploaded documents."

    return {"query": req.query, "answer": answer, "chunks": top}


def keyword_score(query: str, text: str) -> float:
    """Simple TF-like keyword scoring. Use embeddings in production."""
    terms = [t for t in query.split() if len(t) > 1]
    if not terms:
        return 0.0
    hits = sum(1 for t in terms if t in text)
    return hits / len(terms)


def synthesize_answer(query: str, chunks: list[dict]) -> str:
    """Mock answer synthesis. Replace with LLM call in production."""
    sources = "\n".join(f"- {c['file_name']}: \"{c['text'][:120]}...\"" for c in chunks[:3])
    return (
        f"Based on keyword matching across uploaded documents, "
        f"{len(chunks)} relevant passage(s) were found.\n\n"
        f"Top sources:\n{sources}\n\n"
        f"Note: This is a simple keyword-based demo. For production use, integrate "
        f"an embedding model (e.g., text-embedding-3-small) + vector store + LLM "
        f"for semantic retrieval and answer generation."
    )


# ─── Serve frontend in production ────────────────────────────────────

front_path = Path(__file__).parent.parent / "front"
if front_path.exists():
    app.mount("/", StaticFiles(directory=str(front_path), html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
