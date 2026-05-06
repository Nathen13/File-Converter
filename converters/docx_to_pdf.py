"""DOCX -> PDF using docx2pdf.

On Windows this drives Microsoft Word via COM automation. Requires Word
to be installed.
"""
from pathlib import Path
from typing import Optional

from .base import (
    BaseConverter,
    CancelCheck,
    ConversionError,
    ProgressCallback,
)


class DocxToPdfConverter(BaseConverter):
    input_ext = "docx"
    output_ext = "pdf"
    # Word's COM call is one indivisible operation -- we can't poll
    # for cancellation while it's blocked inside Word.
    supports_progress = False
    supports_cancel = False

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
    ) -> None:
        del progress_callback, cancel_check  # unused for this converter

        try:
            from docx2pdf import convert as docx2pdf_convert

            docx2pdf_convert(str(input_path), str(output_path))
        except Exception as e:
            raise ConversionError(
                "DOCX to PDF failed. Microsoft Word must be installed on this "
                f"machine. Underlying error: {e}"
            ) from e
