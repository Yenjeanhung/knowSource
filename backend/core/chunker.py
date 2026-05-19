from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings


def split_text(content: str, metadata: dict = None) -> list[dict]:
    """将文本递归分块。

    返回: [{"index": int, "content": str, "metadata": dict}, ...]
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "。", "！", "？", ".", " ", ""],
    )
    chunks = splitter.split_text(content)
    return [
        {"index": i, "content": chunk, "metadata": metadata or {}}
        for i, chunk in enumerate(chunks)
    ]
