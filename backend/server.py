"""
MiniRAG Backend — KB-based chunked upload + RAG retrieval server.
Run: pip install fastapi uvicorn python-multipart && python server.py
"""
import os
import json
import shutil
import uuid
from datetime import datetime
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

# ─── Registries ────────────────────────────────────────────────────────

kb_registry: dict[str, dict] = {}   # kb_id -> {id, name, created_at, files: {file_id, ...}}
file_registry: dict[str, dict] = {} # file_id -> {name, size, kb_id, status, path}


# ─── Pydantic models ───────────────────────────────────────────────────

class CreateKBRequest(BaseModel):
    name: str

class QueryRequest(BaseModel):
    query: str
    kb_id: str
    top_k: int = 5


# ─── KB CRUD ───────────────────────────────────────────────────────────

@app.post("/api/kb")
async def create_kb(req: CreateKBRequest):
    kb_id = uuid.uuid4().hex[:12]
    kb_registry[kb_id] = {
        "id": kb_id,
        "name": req.name.strip(),
        "created_at": datetime.now().isoformat(),
        "files": {},
    }
    return kb_registry[kb_id]


@app.get("/api/kb")
async def list_kbs():
    return [
        {
            "id": info["id"],
            "name": info["name"],
            "created_at": info["created_at"],
            "file_count": len(info["files"]),
        }
        for info in kb_registry.values()
    ]


@app.get("/api/kb/{kb_id}")
async def get_kb(kb_id: str):
    if kb_id not in kb_registry:
        raise HTTPException(404, "Knowledge base not found")
    kb = kb_registry[kb_id]
    files = []
    for fid in kb["files"]:
        f = file_registry.get(fid)
        if f:
            files.append({
                "id": fid,
                "name": f["name"],
                "size": f["size"],
                "status": f.get("status", "unknown"),
            })
    return {
        "id": kb["id"],
        "name": kb["name"],
        "created_at": kb["created_at"],
        "file_count": len(kb["files"]),
        "files": files,
    }


@app.delete("/api/kb/{kb_id}")
async def delete_kb(kb_id: str):
    if kb_id not in kb_registry:
        raise HTTPException(404, "Knowledge base not found")
    kb = kb_registry.pop(kb_id)
    # Remove all files in this KB
    for fid in list(kb["files"].keys()):
        _remove_file_internal(fid)
    # Remove KB upload dir
    kb_dir = UPLOAD_DIR / kb_id
    if kb_dir.exists():
        shutil.rmtree(kb_dir)
    return {"status": "deleted"}


# ─── File chunk upload ───────────────────────────────────────────────

@app.post("/api/upload/chunk")
async def upload_chunk(
    file_id: str = Form(...),
    file_name: str = Form(...),
    file_size: int = Form(...),
    kb_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    chunk: UploadFile = File(...),
):
    if kb_id not in kb_registry:
        raise HTTPException(404, "Knowledge base not found")

    # Register file on first chunk
    if file_id not in file_registry:
        file_registry[file_id] = {
            "name": file_name,
            "size": file_size,
            "kb_id": kb_id,
            "chunks": [],
            "total_chunks": total_chunks,
        }
        kb_registry[kb_id]["files"][file_id] = True

    # Save chunk
    chunk_path = CHUNK_DIR / f"{file_id}_{chunk_index:06d}"
    with open(chunk_path, "wb") as f:
        shutil.copyfileobj(chunk.file, f)

    file_registry[file_id]["chunks"].append(chunk_index)

    # If all chunks received, reassemble
    if len(file_registry[file_id]["chunks"]) == total_chunks:
        _reassemble_file(file_id)

    return {"status": "ok", "chunk_index": chunk_index, "received": len(file_registry[file_id]["chunks"])}


def _reassemble_file(file_id: str):
    info = file_registry[file_id]
    kb_dir = UPLOAD_DIR / info["kb_id"]
    kb_dir.mkdir(exist_ok=True)
    target_path = kb_dir / info["name"]
    chunk_indices = sorted(info["chunks"])

    with open(target_path, "wb") as out:
        for idx in chunk_indices:
            cp = CHUNK_DIR / f"{file_id}_{idx:06d}"
            with open(cp, "rb") as cin:
                out.write(cin.read())
            cp.unlink()

    info["status"] = "done"
    info["path"] = str(target_path)


# ─── File management ────────────────────────────────────────────────

@app.get("/api/files")
async def list_files():
    return [
        {
            "id": fid,
            "name": info["name"],
            "size": info["size"],
            "kb_id": info.get("kb_id"),
            "status": info.get("status", "uploading"),
        }
        for fid, info in file_registry.items()
    ]


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    if file_id not in file_registry:
        raise HTTPException(404, "File not found")
    _remove_file_internal(file_id)
    return {"status": "deleted"}


def _remove_file_internal(file_id: str):
    info = file_registry.pop(file_id)
    # Remove from parent KB
    kb_id = info.get("kb_id")
    if kb_id and kb_id in kb_registry:
        kb_registry[kb_id]["files"].pop(file_id, None)
    # Remove file
    fp = Path(info.get("path", ""))
    if fp.exists():
        fp.unlink()
    # Clean any leftover chunks
    for cf in CHUNK_DIR.glob(f"{file_id}_*"):
        cf.unlink()


# ─── RAG Query ───────────────────────────────────────────────────────

@app.post("/api/query")
async def query_rag(req: QueryRequest):
    if req.kb_id not in kb_registry:
        raise HTTPException(404, "Knowledge base not found")

    kb = kb_registry[req.kb_id]
    results = []

    for fid in kb["files"]:
        info = file_registry.get(fid)
        if not info or info.get("status") != "done":
            continue

        fp = Path(info.get("path", ""))
        if not fp.exists():
            continue

        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        for p in paragraphs:
            score = _keyword_score(req.query.lower(), p.lower())
            if score > 0:
                results.append({
                    "file_id": fid,
                    "file_name": info["name"],
                    "text": p[:500],
                    "score": min(score, 0.99),
                })

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[: req.top_k]
    answer = _synthesize_answer(req.query, top) if top else "No relevant content found in the knowledge base."
    return {"query": req.query, "answer": answer, "chunks": top}


def _keyword_score(query: str, text: str) -> float:
    terms = [t for t in query.split() if len(t) > 1]
    if not terms:
        return 0.0
    hits = sum(1 for t in terms if t in text)
    return hits / len(terms)


def _synthesize_answer(query: str, chunks: list[dict]) -> str:
    sources = "\n".join(f"- {c['file_name']}: \"{c['text'][:120]}...\"" for c in chunks[:3])
    return (
        f"Based on keyword matching across the knowledge base, "
        f"{len(chunks)} relevant passage(s) were found.\n\n"
        f"Top sources:\n{sources}\n\n"
        f"Note: This is a simple keyword-based demo. For production use, integrate "
        f"an embedding model (e.g., text-embedding-3-small) + vector store + LLM "
        f"for semantic retrieval and answer generation."
    )


# ─── Serve frontend ────────────────────────────────────────────────────

front_path = Path(__file__).parent.parent / "front"
if front_path.exists():
    app.mount("/", StaticFiles(directory=str(front_path), html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
