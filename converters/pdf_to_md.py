"""PDF -> Markdown using pymupdf4llm, page by page.

Page-by-page extraction gives us two things:
  1. Real progress reporting (after each page)
  2. Cooperative cancellation (we check between pages)
"""
from pathlib import Path
from typing import Optional

from .base import (
    BaseConverter,
    CancelCheck,
    ConversionCancelled,
    ConversionError,
    ProgressCallback,
)


class PdfToMarkdownConverter(BaseConverter):
    input_ext = "pdf"
    output_ext = "md"
    supports_progress = True
    supports_cancel = True

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
    ) -> None:
        try:
            import pymupdf
            import pymupdf4llm

            doc = pymupdf.open(str(input_path))
            try:
                total_pages = doc.page_count
                if total_pages == 0:
                    raise ConversionError("PDF has no pages.")

                if progress_callback is not None:
                    progress_callback(0, total_pages)

                chunks: list[str] = []
                for page_index in range(total_pages):
                    # Cancellation checkpoint: check before doing the
                    # next page's work, not after. That way we don't
                    # waste time extracting a page we're about to throw
                    # away.
                    if cancel_check is not None and cancel_check():
                        raise ConversionCancelled(
                            f"Cancelled after {page_index} of {total_pages} pages"
                        )

                    page_md = pymupdf4llm.to_markdown(
                        doc, pages=[page_index], show_progress=False
                    )
                    chunks.append(page_md)

                    if progress_callback is not None:
                        progress_callback(page_index + 1, total_pages)

                combined = "\n\n".join(chunks)

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
            # Includes ConversionCancelled. Re-raise as-is so the GUI
            # can distinguish.
            raise
        except Exception as e:
            raise ConversionError(f"PDF to Markdown failed: {e}") from e
