"""Main application window.

Adds real progress reporting for converters that support it (currently
PDF -> MD): determinate progress bar, elapsed time, and ETA.
"""
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
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
    """Runs a single conversion off the UI thread.

    Signals:
        progress(current, total) -- emitted by the converter via callback.
                                    For converters that don't report progress,
                                    this is never emitted.
        finished_ok(output_path)
        finished_err(error_message)
    """

    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(str)
    finished_err = pyqtSignal(str)

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

    def _on_progress(self, current: int, total: int) -> None:
        # The converter calls this from the worker thread. Emitting a
        # Qt signal hops it onto the main thread safely.
        self.progress.emit(current, total)

    def run(self) -> None:
        try:
            self._converter.convert(
                self._input_path,
                self._output_path,
                progress_callback=self._on_progress,
            )
            self.finished_ok.emit(str(self._output_path))
        except Exception as e:
            self.finished_err.emit(str(e))


def _format_duration(seconds: float) -> str:
    """Format duration: 0.4s, 12.3s, M:SS, or H:MM:SS."""
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds:.1f}s"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("File Converter")
        self.setMinimumSize(540, 320)

        self._input_path: Optional[Path] = None
        self._worker: Optional[ConversionWorker] = None

        # Tracking for elapsed/ETA. _start_time is the wall-clock moment
        # conversion began. _last_progress is the most recent (current,
        # total) tuple from the worker; we use it to compute ETA each
        # tick of the elapsed-timer.
        self._start_time: Optional[float] = None
        self._last_progress: Optional[tuple[int, int]] = None

        # Drives the elapsed/ETA labels at 4 Hz so they feel live even
        # between progress callbacks (which on a long page can be
        # several seconds apart).
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(250)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        self._build_ui()

    # ---------- UI construction ----------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)

        # File selection row
        file_row = QHBoxLayout()
        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("color: gray;")
        select_btn = QPushButton("Select File\u2026")
        select_btn.clicked.connect(self._on_select_file)
        file_row.addWidget(self.file_label, stretch=1)
        file_row.addWidget(select_btn)
        layout.addLayout(file_row)

        # Format selection row
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Convert to:"))
        self.format_combo = QComboBox()
        self.format_combo.setEnabled(False)
        format_row.addWidget(self.format_combo, stretch=1)
        layout.addLayout(format_row)

        # Convert button
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setEnabled(False)
        self.convert_btn.clicked.connect(self._on_convert)
        layout.addWidget(self.convert_btn)

        # Progress bar (mode set per-conversion)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Timing row: elapsed on the left, ETA on the right
        timing_row = QHBoxLayout()
        self.elapsed_label = QLabel("")
        self.eta_label = QLabel("")
        self.eta_label.setStyleSheet("color: gray;")
        timing_row.addWidget(self.elapsed_label)
        timing_row.addStretch()
        timing_row.addWidget(self.eta_label)
        self.elapsed_label.setVisible(False)
        self.eta_label.setVisible(False)
        layout.addLayout(timing_row)

        # Status text (success / error)
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
        # UI state for "in progress"
        self.convert_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.elapsed_label.setVisible(True)
        self.eta_label.setVisible(True)
        self.eta_label.setText("")
        self._set_status(f"Converting\u2026", color="")

        # Configure progress bar based on whether the converter can report
        # real progress. Determinate mode = real percentage; indeterminate
        # mode = animated spinner.
        if converter.supports_progress:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")
        else:
            self.progress_bar.setRange(0, 0)  # spinner
            self.progress_bar.setFormat("")

        # Start timing
        self._start_time = time.monotonic()
        self._last_progress = None
        self.elapsed_label.setText("Elapsed: 0:00")
        self._elapsed_timer.start()

        # Spin up the worker
        self._worker = ConversionWorker(converter, input_path, output_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_conversion_ok)
        self._worker.finished_err.connect(self._on_conversion_err)
        self._worker.start()

    # ---------- Progress / timer handlers ----------
    def _on_progress(self, current: int, total: int) -> None:
        self._last_progress = (current, total)
        if total > 0:
            pct = int(round(current / total * 100))
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{current}/{total} pages  \u2014  %p%")

    def _tick_elapsed(self) -> None:
        """Updates elapsed and ETA labels four times per second."""
        if self._start_time is None:
            return
        elapsed = time.monotonic() - self._start_time
        self.elapsed_label.setText(f"Elapsed: {_format_duration(elapsed)}")

        # ETA only if we have at least 2 pages of data (1 page is too
        # noisy; first-page costs include lazy library initialization).
        if self._last_progress is not None:
            current, total = self._last_progress
            if current >= 2 and current < total:
                per_unit = elapsed / current
                remaining = per_unit * (total - current)
                self.eta_label.setText(
                    f"ETA: ~{_format_duration(remaining)} remaining"
                )
            elif current >= total > 0:
                self.eta_label.setText("Finalizing\u2026")

    # ---------- Completion handlers ----------
    def _on_conversion_ok(self, output_path: str) -> None:
        self._stop_timing()
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.elapsed_label.setVisible(False)
        self.eta_label.setVisible(False)
        self.convert_btn.setEnabled(True)

        elapsed_str = (
            _format_duration(time.monotonic() - self._start_time)
            if self._start_time
            else "?"
        )
        self._set_status(
            f"\u2713 Saved to: {output_path}  (took {elapsed_str})",
            color="green",
        )

    def _on_conversion_err(self, message: str) -> None:
        self._stop_timing()
        self.progress_bar.setVisible(False)
        self.elapsed_label.setVisible(False)
        self.eta_label.setVisible(False)
        self.convert_btn.setEnabled(True)
        self._set_status(f"\u2717 {message}", color="red")
        QMessageBox.critical(self, "Conversion failed", message)

    def _stop_timing(self) -> None:
        self._elapsed_timer.stop()
        # Don't clear _start_time yet -- _on_conversion_ok reads it for
        # the final "took N:SS" message.

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};" if color else "")
