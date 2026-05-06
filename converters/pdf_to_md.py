"""PDF -> Markdown using pymupdf4llm (PyMuPDF's LLM-friendly extractor)."""
from pathlib import Path

from .base import BaseConverter, ConversionError


class PdfToMarkdownConverter(BaseConverter):
    input_ext = "pdf"
    output_ext = "md"

    def convert(self, input_path: Path, output_path: Path) -> None:
        try:
            # Imported lazily so app startup stays fast and PyInstaller
            # only pulls it in when actually used.
            import pymupdf4llm

            md_text = pymupdf4llm.to_markdown(str(input_path))
            output_path.write_text(md_text, encoding="utf-8")
        except Exception as e:
            raise ConversionError(f"PDF to Markdown failed: {e}") from e
