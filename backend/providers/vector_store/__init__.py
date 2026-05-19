"""向量存储工厂（LangChain 封装）。"""

from langchain_core.embeddings import Embeddings

from config import settings


def create_vector_store(kb_id: str, embeddings: Embeddings):
    """为指定知识库创建向量存储实例（每个 KB 独立 Collection）。"""
    if settings.VECTOR_STORE_PROVIDER == "chroma":
        from langchain_chroma import Chroma
        return Chroma(
            collection_name=kb_id,
            embedding_function=embeddings,
            persist_directory=settings.CHROMA_PERSIST_DIR,
            collection_metadata={"hnsw:space": "cosine"},
        )
    elif settings.VECTOR_STORE_PROVIDER == "milvus":
        from langchain_milvus import Milvus
        return Milvus(
            collection_name=kb_id,
            embedding_function=embeddings,
            connection_args={"host": settings.MILVUS_HOST, "port": settings.MILVUS_PORT},
        )
    raise ValueError(f"未知的向量存储 Provider: {settings.VECTOR_STORE_PROVIDER}")


def delete_kb_collection(kb_id: str):
    """删除知识库对应的向量 Collection。"""
    if settings.VECTOR_STORE_PROVIDER == "chroma":
        import chromadb
        client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        try:
            client.delete_collection(kb_id)
        except Exception:
            pass
    elif settings.VECTOR_STORE_PROVIDER == "milvus":
        # TODO: Milvus collection 删除
        pass
