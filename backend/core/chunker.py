import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings


def _find_page(page_map, start, end):
    """根据字符偏移量反查 PDF 页码。"""
    if not page_map:
        return None
    mid = (start + end) // 2
    for pm in page_map:
        if pm["start"] <= mid < pm["end"]:
            return pm["page_number"]
    return None


def _build_result(content: str, chunks: list[str], metadata: dict) -> list[dict]:
    """为切分后的文本列表构建统一返回格式。"""
    page_map = (metadata or {}).get("page_map")
    result = []
    offset = 0
    for i, chunk in enumerate(chunks):
        start_offset = content.find(chunk, offset)
        if start_offset == -1:
            start_offset = offset
        end_offset = start_offset + len(chunk)
        offset = start_offset + 1

        result.append({
            "index": i,
            "content": chunk,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "page_number": _find_page(page_map, start_offset, end_offset),
            "metadata": metadata or {},
        })
    return result


# ---- fixed: 固定大小递归切分 ----

def _split_fixed(content: str, metadata: dict) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "。", "！", "？", ".", " ", ""],
    )
    chunks = splitter.split_text(content)
    return _build_result(content, chunks, metadata)


# ---- sentence: 按句子切分 ----

_SENT_SEP = re.compile(r'(?<=[。！？；\n])')

def _split_sentence(content: str, metadata: dict) -> list[dict]:
    """按句子边界切分，每 N 个字符合并一个 chunk。"""
    sentences = [s for s in _SENT_SEP.split(content) if s.strip()]
    chunks = []
    buf = []
    buf_len = 0

    for s in sentences:
        if buf_len + len(s) > settings.CHUNK_SIZE and buf:
            chunks.append("".join(buf))
            # 保留 overlap 部分
            overlap_text = "".join(buf)[-settings.CHUNK_OVERLAP:]
            buf = [overlap_text] if overlap_text else []
            buf_len = len(buf[0]) if buf else 0
        buf.append(s)
        buf_len += len(s)

    if buf:
        chunks.append("".join(buf))

    return _build_result(content, chunks, metadata)


# ---- semantic: 语义分块 ----

def _split_semantic(content: str, metadata: dict) -> list[dict]:
    """按段落和章节结构切分，尽量保持语义完整性。"""
    # 先按双换行（段落）切
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    chunks = []
    buf = []
    buf_len = 0

    for para in paragraphs:
        # 单段超长则进一步按句子拆
        if len(para) > settings.CHUNK_SIZE:
            if buf:
                chunks.append("\n\n".join(buf))
                buf = []
                buf_len = 0
            sub_sentences = [s for s in _SENT_SEP.split(para) if s.strip()]
            sub_buf = []
            sub_len = 0
            for s in sub_sentences:
                if sub_len + len(s) > settings.CHUNK_SIZE and sub_buf:
                    chunks.append("".join(sub_buf))
                    sub_buf = [s]
                    sub_len = len(s)
                else:
                    sub_buf.append(s)
                    sub_len += len(s)
            if sub_buf:
                chunks.append("".join(sub_buf))
            continue

        if buf_len + len(para) > settings.CHUNK_SIZE and buf:
            chunks.append("\n\n".join(buf))
            buf = []
            buf_len = 0

        buf.append(para)
        buf_len += len(para)

    if buf:
        chunks.append("\n\n".join(buf))

    return _build_result(content, chunks, metadata)


# ---- 入口 ----

_STRATEGIES = {
    "fixed": _split_fixed,
    "sentence": _split_sentence,
    "semantic": _split_semantic,
}


def split_text(content: str, metadata: dict = None) -> list[dict]:
    """按配置的策略分块。

    返回: [{"index", "content", "start_offset", "end_offset", "page_number", "metadata"}, ...]
    """
    strategy = settings.CHUNK_STRATEGY
    fn = _STRATEGIES.get(strategy, _split_fixed)
    return fn(content, metadata or {})
