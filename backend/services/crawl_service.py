from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import async_session
from models import CrawlJob
from services.library_service import ASSET_DIR, LibraryService


def _now_iso() -> str:
    return datetime.now().isoformat()


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = False
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = True
        if tag in {"p", "div", "section", "article", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = False
        if tag in {"p", "div", "section", "article", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.parts.append(text)

    def text(self) -> str:
        content = " ".join(self.parts)
        content = re.sub(r"\s+", " ", content)
        content = re.sub(r"\s*\n\s*", "\n", content)
        return unescape(content).strip()


def _job_to_dict(job: CrawlJob) -> dict:
    return {
        "id": job.id,
        "keyword": job.keyword,
        "directory_id": job.directory_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "urls": json.loads(job.urls or "[]"),
        "file_count": job.file_count,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


def _fetch_url(url: str, timeout: int) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            )
        },
    )
    with urlopen(req, timeout=timeout) as response:
        raw = response.read(2 * 1024 * 1024)
        content_type = response.headers.get("content-type", "")
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        charset = match.group(1)
    return raw.decode(charset, errors="ignore")


def _extract_title(html: str, fallback: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not match:
        return fallback
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return unescape(title)[:120] or fallback


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _normalize_search_url(url: str) -> str | None:
    if not url:
        return None
    url = unescape(url)
    if url.startswith("//"):
        url = "https:" + url
    if "duckduckgo.com/l/" in url:
        parsed = urlparse(url)
        value = parse_qs(parsed.query).get("uddg", [""])[0]
        url = unquote(value)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if "duckduckgo.com" in parsed.netloc:
        return None
    return url


def _search_web(keyword: str, limit: int, timeout: int) -> list[str]:
    search_url = f"https://duckduckgo.com/html/?q={quote_plus(keyword)}"
    html = _fetch_url(search_url, timeout)
    candidates = re.findall(r'href="([^"]+)"[^>]*class="result__a"', html)
    if not candidates:
        candidates = re.findall(r'class="result__a"[^>]*href="([^"]+)"', html)
    urls: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        url = _normalize_search_url(item)
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _clean_thinking(content: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>", "", content).strip()


def _summarize_with_llm(keyword: str, documents: list[dict], depth: str = "medium") -> tuple[str, str]:
    joined = "\n\n".join(
        f"来源：{item['url']}\n标题：{item['title']}\n正文摘录：{item['text'][:5000]}"
        for item in documents
    )
    
    depth_config = {
        "low": {
            "prompt_suffix": "要求：简洁整理，保留核心事实和来源链接，给出 3 条要点。",
            "max_length": 12000,
            "text_limit": 2000,
        },
        "medium": {
            "prompt_suffix": "要求：保留事实边界，不要编造；按主题分节；列出来源链接；最后给出 5 条要点。",
            "max_length": 24000,
            "text_limit": 3000,
        },
        "high": {
            "prompt_suffix": "要求：详细分析整理，深入挖掘信息；按主题分节并展开子主题；列出来源链接；给出 8-10 条要点；提供多角度分析。",
            "max_length": 40000,
            "text_limit": 5000,
        },
    }
    
    config = depth_config.get(depth, depth_config["medium"])
    
    fallback = "\n\n".join(
        f"## {item['title']}\n\n来源：{item['url']}\n\n{item['text'][:config['text_limit']]}"
        for item in documents
    )
    try:
        from providers.llm import create_llm

        llm = create_llm()
        prompt = (
            f"你是资料采集助手。请基于给定网页摘录，整理一份可进入知识库的中文 Markdown 文档。\n"
            f"{config['prompt_suffix']}\n\n"
            f"关键词：{keyword}\n\n{joined[:config['max_length']]}"
        )
        response = llm.invoke(prompt)
        content = getattr(response, "content", str(response)).strip()
        content = _clean_thinking(content)
        if content:
            summary = content.split("\n", 1)[0].strip("# ").strip()[:200]
            return content, summary or f"{keyword} 采集资料"
    except Exception:
        pass
    return fallback, f"{keyword} 采集资料"


class CrawlService:
    @staticmethod
    async def create_job(
        db: AsyncSession,
        keyword: str,
        *,
        directory_id: str | None = None,
        max_pages: int | None = None,
        auto_attach_kb_id: str | None = None,
        auto_process: bool = False,
        extract_graph: bool = True,
        analysis_depth: str = "medium",
    ) -> dict:
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("Keyword is required")
        if not settings.CRAWL_ENABLED:
            raise ValueError("Crawl is disabled")

        if directory_id is None:
            directory = await LibraryService.default_crawl_directory(db, keyword)
            directory_id = directory.id

        job = CrawlJob(
            keyword=keyword,
            directory_id=directory_id,
            status="queued",
            progress=0,
            message="等待采集",
            urls="[]",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        asyncio.create_task(
            CrawlService._run_job(
                job.id,
                max_pages=max_pages,
                auto_attach_kb_id=auto_attach_kb_id,
                auto_process=auto_process,
                extract_graph=extract_graph,
                analysis_depth=analysis_depth,
            )
        )
        return _job_to_dict(job)

    @staticmethod
    async def get_job(db: AsyncSession, job_id: str) -> dict | None:
        job = await db.get(CrawlJob, job_id)
        return _job_to_dict(job) if job else None

    @staticmethod
    async def get_latest_job(db: AsyncSession) -> dict | None:
        from sqlalchemy import select, desc
        result = await db.execute(
            select(CrawlJob).order_by(desc(CrawlJob.created_at)).limit(1)
        )
        job = result.scalar_one_or_none()
        return _job_to_dict(job) if job else None

    @staticmethod
    async def _set_job_state(
        db: AsyncSession,
        job: CrawlJob,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        urls: list[str] | None = None,
        file_count: int | None = None,
        finished: bool = False,
    ):
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = max(0, min(100, progress))
        if message is not None:
            job.message = message[:300]
        if urls is not None:
            job.urls = json.dumps(urls, ensure_ascii=False)
        if file_count is not None:
            job.file_count = file_count
        if finished:
            job.finished_at = _now_iso()
        await db.commit()

    @staticmethod
    async def _run_job(
        job_id: str,
        *,
        max_pages: int | None,
        auto_attach_kb_id: str | None,
        auto_process: bool,
        extract_graph: bool,
        analysis_depth: str = "medium",
    ):
        async with async_session() as db:
            job = await db.get(CrawlJob, job_id)
            if not job:
                return
            try:
                limit = max(1, min(max_pages or settings.CRAWL_MAX_PAGES, 20))
                await CrawlService._set_job_state(
                    db,
                    job,
                    status="running",
                    progress=5,
                    message="正在搜索互联网资料",
                )
                urls = await asyncio.to_thread(
                    _search_web,
                    job.keyword,
                    limit,
                    settings.CRAWL_TIMEOUT_SECONDS,
                )
                if not urls:
                    raise RuntimeError("未搜索到可采集网页")

                await CrawlService._set_job_state(
                    db,
                    job,
                    progress=20,
                    message=f"搜索完成，准备抓取 {len(urls)} 个网页",
                    urls=urls,
                )

                documents: list[dict] = []
                for index, url in enumerate(urls, start=1):
                    await CrawlService._set_job_state(
                        db,
                        job,
                        progress=20 + int(index / max(len(urls), 1) * 45),
                        message=f"正在抓取网页 {index}/{len(urls)}",
                    )
                    try:
                        html = await asyncio.to_thread(_fetch_url, url, settings.CRAWL_TIMEOUT_SECONDS)
                        title = _extract_title(html, url)
                        text = _html_to_text(html)
                        if len(text) >= 200:
                            documents.append({"url": url, "title": title, "text": text})
                    except Exception:
                        continue
                    if settings.CRAWL_RATE_LIMIT_SECONDS > 0:
                        await asyncio.to_thread(time.sleep, settings.CRAWL_RATE_LIMIT_SECONDS)

                if not documents:
                    raise RuntimeError("网页抓取失败或正文过短")

                await CrawlService._set_job_state(
                    db,
                    job,
                    progress=75,
                    message="正在调用大模型清洗整理资料",
                )
                markdown, summary = await asyncio.to_thread(_summarize_with_llm, job.keyword, documents, analysis_depth)

                ASSET_DIR.mkdir(parents=True, exist_ok=True)
                file_id = uuid.uuid4().hex[:12]
                source_path = ASSET_DIR / f"{file_id}_crawl.md"
                source_lines = "\n".join(f"- {item['title']}: {item['url']}" for item in documents)
                source_path.write_text(
                    (
                        f"---\nkeyword: {job.keyword}\ncrawled_at: {_now_iso()}\n"
                        f"sources: {len(documents)}\n---\n\n"
                        f"# {job.keyword}\n\n## 来源\n\n{source_lines}\n\n## 整理内容\n\n{markdown}\n"
                    ),
                    encoding="utf-8",
                )
                asset = await LibraryService.create_asset_from_path(
                    db,
                    source_path,
                    name=f"{job.keyword}.md",
                    directory_id=job.directory_id,
                    source_type="crawl",
                    source_url=documents[0]["url"],
                    source_keyword=job.keyword,
                    summary=summary,
                    move=True,
                )

                if auto_attach_kb_id:
                    await LibraryService.attach_assets_to_kb(
                        db,
                        auto_attach_kb_id,
                        [asset.id],
                        auto_process=auto_process,
                        extract_graph=extract_graph,
                    )

                await CrawlService._set_job_state(
                    db,
                    job,
                    status="done",
                    progress=100,
                    message="采集完成，已保存到文件管理",
                    file_count=1,
                    finished=True,
                )
            except Exception as exc:
                await CrawlService._set_job_state(
                    db,
                    job,
                    status="failed",
                    message=f"采集失败：{exc}",
                    finished=True,
                )
