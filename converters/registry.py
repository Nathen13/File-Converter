"""Registry of available converters.

To add a new format pair:
1. Create a new module in this package subclassing BaseConverter.
2. Append an instance to CONVERTERS below.
That's it. The GUI auto-discovers what's available.
"""
from .base import BaseConverter
from .docx_to_pdf import DocxToPdfConverter
from .pdf_to_md import PdfToMarkdownConverter
from .txt_to_html import TxtToHtmlConverter


CONVERTERS: list[BaseConverter] = [
    PdfToMarkdownConverter(),
    DocxToPdfConverter(),
    TxtToHtmlConverter(),
]


def get_converter(input_ext: str, output_ext: str) -> BaseConverter | None:
    """Return the converter matching the (input, output) pair, or None."""
    input_ext = input_ext.lower().lstrip(".")
    output_ext = output_ext.lower().lstrip(".")
    for c in CONVERTERS:
        if c.input_ext == input_ext and c.output_ext == output_ext:
            return c
    return None


def get_supported_outputs(input_ext: str) -> list[str]:
    """List output extensions available for the given input extension."""
    input_ext = input_ext.lower().lstrip(".")
    return [c.output_ext for c in CONVERTERS if c.input_ext == input_ext]


def get_supported_inputs() -> list[str]:
    """All input extensions that have at least one converter."""
    return sorted({c.input_ext for c in CONVERTERS})
