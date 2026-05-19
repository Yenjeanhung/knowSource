from pathlib import Path

from providers.parser.base import DocumentParser, ParseResult


class PdfParser(DocumentParser):
    """PDF 文档解析器。"""

    def parse(self, file_path: Path) -> ParseResult:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return ParseResult(
            filename=file_path.name,
            format=".pdf",
            content="\n\n".join(pages),
            metadata={"pages": len(reader.pages)},
        )

    def supported_extensions(self) -> list[str]:
        return [".pdf"]
