"""TXT -> HTML. Wraps text in a styled, escaped HTML document."""
import html
from pathlib import Path

from .base import BaseConverter, ConversionError


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    max-width: 800px;
    margin: 2em auto;
    padding: 0 1em;
    line-height: 1.6;
    color: #1f2328;
  }}
  pre {{
    white-space: pre-wrap;
    word-wrap: break-word;
    background: #f6f8fa;
    padding: 1em;
    border-radius: 6px;
    font-family: "Consolas", "Cascadia Code", monospace;
  }}
</style>
</head>
<body>
<h1>{title}</h1>
<pre>{content}</pre>
</body>
</html>
"""


class TxtToHtmlConverter(BaseConverter):
    input_ext = "txt"
    output_ext = "html"

    def convert(self, input_path: Path, output_path: Path) -> None:
        try:
            # utf-8-sig handles Windows files that include a BOM (common
            # when saved from Notepad).
            content = input_path.read_text(encoding="utf-8-sig")
            doc = HTML_TEMPLATE.format(
                title=html.escape(input_path.stem),
                content=html.escape(content),
            )
            output_path.write_text(doc, encoding="utf-8")
        except Exception as e:
            raise ConversionError(f"TXT to HTML failed: {e}") from e
