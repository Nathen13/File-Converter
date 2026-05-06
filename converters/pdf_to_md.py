"""PDF -> Markdown using pymupdf4llm, page by page so we can report progress.

The straightforward `pymupdf4llm.to_markdown(file)` call processes the
whole document in one shot and gives no progress hook. To show real
progress, we open the PDF ourselves with pymupdf, iterate pages, and
extract one page at a time.
"""
from pathlib import Path
from typing import Optional

from .base import BaseConverter, ConversionError, ProgressCallback


class PdfToMarkdownConverter(BaseConverter):
    input_ext = "pdf"
    output_ext = "md"
    supports_progress = True

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        try:
            # Lazy imports keep app startup fast and let PyInstaller's
            # collect_data_files hook still pull these in correctly.
            import pymupdf
            import pymupdf4llm

            # Open the document once so we know the page count upfront
            # and can pass it to to_markdown() per page.
            doc = pymupdf.open(str(input_path))
            try:
                total_pages = doc.page_count
                if total_pages == 0:
                    raise ConversionError("PDF has no pages.")

                # Initial signal so the UI knows the total before we
                # start chewing through pages.
                if progress_callback is not None:
                    progress_callback(0, total_pages)

                chunks: list[str] = []
                for page_index in range(total_pages):
                    # `pages` accepts a list of 0-based page indices.
                    # Passing one page at a time gives us per-page progress
                    # at the cost of a little overhead per page (acceptable
                    # — pymupdf4llm's per-page work dominates).
                    page_md = pymupdf4llm.to_markdown(
                        doc, pages=[page_index], show_progress=False
                    )
                    chunks.append(page_md)

                    if progress_callback is not None:
                        progress_callback(page_index + 1, total_pages)

                combined = "\n\n".join(chunks)

                # If extraction produced nothing meaningful, the PDF likely
                # has no extractable text -- e.g. a scanned image-only PDF
                # without OCR, or a genuinely blank document. Surface this
                # as an error rather than silently writing an empty file.
                if not combined.strip():
                    raise ConversionError(
                        "No text could be extracted from this PDF. It may be "
                        "blank, image-only (scanned without OCR), or "
                        "encrypted. Nothing was saved."
                    )

                output_path.write_text(combined, encoding="utf-8")
            finally:
                doc.close()
        except ConversionError:
            raise
        except Exception as e:
            raise ConversionError(f"PDF to Markdown failed: {e}") from e
