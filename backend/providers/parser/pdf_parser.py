from pathlib import Path

from providers.parser.base import DocumentParser, ParseResult


class PdfParser(DocumentParser):
    """PDF 文档解析器，使用 pypdfium2。"""

    def parse(self, file_path: Path) -> ParseResult:
        import pypdfium2

        pdf = pypdfium2.PdfDocument(str(file_path))
        pages = []
        for page in pdf:
            text_page = page.get_textpage()
            text = text_page.get_text_range()
            pages.append(text or "")
            text_page.close()
            page.close()
        pdf.close()

        return ParseResult(
            filename=file_path.name,
            format=".pdf",
            content="\n\n".join(pages),
            metadata={"pages": len(pages)},
        )

    def supported_extensions(self) -> list[str]:
        return [".pdf"]
