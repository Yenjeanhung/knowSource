from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings


def split_text(content: str, metadata: dict = None) -> list[dict]:
    """将文本递归分块，记录每个 chunk 的字符偏移量。

    如果 metadata 中包含 page_map（PDF），则为每个 chunk 反查页码。

    返回: [{"index": int, "content": str, "start_offset": int, "end_offset": int,
            "page_number": int|None, "metadata": dict}, ...]
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "。", "！", "？", ".", " ", ""],
    )
    chunks = splitter.split_text(content)

    page_map = (metadata or {}).get("page_map")

    result = []
    offset = 0
    for i, chunk in enumerate(chunks):
        start_offset = content.find(chunk, offset)
        if start_offset == -1:
            start_offset = offset
        end_offset = start_offset + len(chunk)
        offset = start_offset + 1

        # 反查页码
        page_number = None
        if page_map:
            mid = (start_offset + end_offset) // 2
            for pm in page_map:
                if pm["start"] <= mid < pm["end"]:
                    page_number = pm["page_number"]
                    break

        result.append({
            "index": i,
            "content": chunk,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "page_number": page_number,
            "metadata": metadata or {},
        })
    return result
