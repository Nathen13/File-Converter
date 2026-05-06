"""DOCX -> PDF using docx2pdf.

On Windows this drives Microsoft Word via COM automation. Requires Word
to be installed. We chose this over Pandoc+LaTeX (huge dependency) and
LibreOffice headless (heavyweight, slow startup) because most Windows
users targeted by this app already have Office installed, and Word's
rendering of DOCX is the de-facto reference.
"""
from pathlib import Path

from .base import BaseConverter, ConversionError


class DocxToPdfConverter(BaseConverter):
    input_ext = "docx"
    output_ext = "pdf"

    def convert(self, input_path: Path, output_path: Path) -> None:
        try:
            # Lazy import: pulls in pywin32/COM bindings only on first use.
            from docx2pdf import convert as docx2pdf_convert

            docx2pdf_convert(str(input_path), str(output_path))
        except Exception as e:
            raise ConversionError(
                "DOCX to PDF failed. Microsoft Word must be installed on this "
                f"machine. Underlying error: {e}"
            ) from e
