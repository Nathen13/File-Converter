# File Converter

A small Windows desktop app for converting between document formats.

## Supported conversions

| From | To       | Engine                                |
| ---- | -------- | ------------------------------------- |
| PDF  | Markdown | `pymupdf4llm` (PyMuPDF)               |
| DOCX | PDF      | `docx2pdf` (Microsoft Word COM)       |
| TXT  | HTML     | Built-in (escaped, styled `<pre>`)    |

## Project structure

```
file_converter/
├── main.py                  # entry point
├── requirements.txt
├── build.spec               # PyInstaller config
├── gui/
│   ├── __init__.py
│   └── main_window.py       # PyQt6 window + worker thread
└── converters/
    ├── __init__.py
    ├── base.py              # BaseConverter ABC + ConversionError
    ├── registry.py          # add new converters here
    ├── pdf_to_md.py
    ├── docx_to_pdf.py
    └── txt_to_html.py
```

## Setup (development)

Requires Python 3.11+ on Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Note on DOCX → PDF

`docx2pdf` drives Microsoft Word via COM automation. Word must be
installed and licensed on the machine. If that's a hard blocker for your
target users, swap the converter implementation for one of:

- Pandoc + a LaTeX engine (large install, no Word required)
- LibreOffice headless via `subprocess` (free, slower startup)
- A direct python-docx + reportlab pipeline (lossy, but pure-Python)

## Build a standalone .exe

```powershell
.\.venv\Scripts\activate
pyinstaller build.spec
```

Output: `dist\FileConverter.exe`

For a single-file .exe (slower to launch but easier to distribute), edit
`build.spec` and set `onefile=True` in the `EXE(...)` call, or use the
quick command:

```powershell
pyinstaller --onefile --windowed --name FileConverter ^
  --hidden-import pymupdf4llm --hidden-import docx2pdf ^
  --hidden-import win32com.client --hidden-import pythoncom ^
  main.py
```

## Adding a new conversion

1. Create `converters/<from>_to_<to>.py` with a class that subclasses
   `BaseConverter`, sets `input_ext`/`output_ext`, and implements
   `convert(input_path, output_path)`.
2. Import the class and append an instance to `CONVERTERS` in
   `converters/registry.py`.

The GUI auto-populates the format dropdown from the registry — no UI
changes needed.
