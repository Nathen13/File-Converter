"""DOCX -> PDF using docx2pdf.

On Windows this drives Microsoft Word via COM automation. Requires Word
to be installed.
"""
from pathlib import Path
from typing import Optional

from .base import BaseConverter, ConversionError, ProgressCallback


class DocxToPdfConverter(BaseConverter):
    input_ext = "docx"
    output_ext = "pdf"
    # Word's COM API doesn't expose progress, so we can't report it.
    supports_progress = False

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        # progress_callback is unused -- Word doesn't tell us how far along
        # it is, so the GUI will show indeterminate progress instead.
        del progress_callback

        try:
            from docx2pdf import convert as docx2pdf_convert

            docx2pdf_convert(str(input_path), str(output_path))
        except Exception as e:
            raise ConversionError(
                "DOCX to PDF failed. Microsoft Word must be installed on this "
                f"machine. Underlying error: {e}"
            ) from e
