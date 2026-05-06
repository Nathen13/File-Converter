"""Main application window.

UI is intentionally minimal: pick a file, pick an output format,
hit Convert. Conversion runs on a QThread so the UI stays responsive
on large files.
"""
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from converters.base import BaseConverter
from converters.registry import (
    CONVERTERS,
    get_converter,
    get_supported_outputs,
)


class ConversionWorker(QThread):
    """Runs a single conversion off the UI thread."""

    finished_ok = pyqtSignal(str)       # output path
    finished_err = pyqtSignal(str)      # error message

    def __init__(
        self,
        converter: BaseConverter,
        input_path: Path,
        output_path: Path,
    ) -> None:
        super().__init__()
        self._converter = converter
        self._input_path = input_path
        self._output_path = output_path

    def run(self) -> None:  # noqa: D401
        try:
            self._converter.convert(self._input_path, self._output_path)
            self.finished_ok.emit(str(self._output_path))
        except Exception as e:  # ConversionError or anything escaped
            self.finished_err.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("File Converter")
        self.setMinimumSize(520, 260)

        self._input_path: Path | None = None
        self._worker: ConversionWorker | None = None

        self._build_ui()

    # ---------- UI construction ----------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)

        # Row 1: file selection
        file_row = QHBoxLayout()
        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("color: gray;")
        select_btn = QPushButton("Select File\u2026")
        select_btn.clicked.connect(self._on_select_file)
        file_row.addWidget(self.file_label, stretch=1)
        file_row.addWidget(select_btn)
        layout.addLayout(file_row)

        # Row 2: output format
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Convert to:"))
        self.format_combo = QComboBox()
        self.format_combo.setEnabled(False)
        format_row.addWidget(self.format_combo, stretch=1)
        layout.addLayout(format_row)

        # Row 3: convert button
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setEnabled(False)
        self.convert_btn.clicked.connect(self._on_convert)
        layout.addWidget(self.convert_btn)

        # Row 4: progress + status
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)  # indeterminate
        layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Footer: list of supported conversions
        supported = ", ".join(c.display_name for c in CONVERTERS)
        hint = QLabel(f"Supported: {supported}")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        layout.addStretch()

    # ---------- Event handlers ----------
    def _on_select_file(self) -> None:
        exts = sorted({c.input_ext for c in CONVERTERS})
        filter_str = (
            "Supported (" + " ".join(f"*.{e}" for e in exts) + ");;All Files (*.*)"
        )
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select File", "", filter_str
        )
        if not path_str:
            return

        self._input_path = Path(path_str)
        self.file_label.setText(self._input_path.name)
        self.file_label.setStyleSheet("")
        self._refresh_format_options()

    def _refresh_format_options(self) -> None:
        assert self._input_path is not None
        ext = self._input_path.suffix.lstrip(".").lower()
        outputs = get_supported_outputs(ext)

        self.format_combo.clear()
        if outputs:
            self.format_combo.addItems([o.upper() for o in outputs])
            self.format_combo.setEnabled(True)
            self.convert_btn.setEnabled(True)
            self._set_status("", color="")
        else:
            self.format_combo.setEnabled(False)
            self.convert_btn.setEnabled(False)
            QMessageBox.warning(
                self,
                "Unsupported format",
                f"No conversions are available for .{ext} files.",
            )

    def _on_convert(self) -> None:
        if self._input_path is None:
            return

        output_ext = self.format_combo.currentText().lower()
        input_ext = self._input_path.suffix.lstrip(".").lower()
        converter = get_converter(input_ext, output_ext)
        if converter is None:
            QMessageBox.critical(self, "Error", "Converter not found.")
            return

        # Default save location: alongside source, with new extension.
        default_name = self._input_path.with_suffix(f".{output_ext}").name
        out_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save As",
            default_name,
            f"{output_ext.upper()} (*.{output_ext})",
        )
        if not out_str:
            return

        output_path = Path(out_str)
        self._start_conversion(converter, self._input_path, output_path)

    def _start_conversion(
        self,
        converter: BaseConverter,
        input_path: Path,
        output_path: Path,
    ) -> None:
        self.convert_btn.setEnabled(False)
        self.progress.setVisible(True)
        self._set_status("Converting\u2026", color="")

        self._worker = ConversionWorker(converter, input_path, output_path)
        self._worker.finished_ok.connect(self._on_conversion_ok)
        self._worker.finished_err.connect(self._on_conversion_err)
        self._worker.start()

    def _on_conversion_ok(self, output_path: str) -> None:
        self.progress.setVisible(False)
        self.convert_btn.setEnabled(True)
        self._set_status(f"\u2713 Saved to: {output_path}", color="green")

    def _on_conversion_err(self, message: str) -> None:
        self.progress.setVisible(False)
        self.convert_btn.setEnabled(True)
        self._set_status(f"\u2717 {message}", color="red")
        QMessageBox.critical(self, "Conversion failed", message)

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};" if color else "")
