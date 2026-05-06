"""Main application window.

UI features:
- Embedded drop zone at the top of the window:
  * Empty state: large dashed-border prompt to drop or click
  * Loaded state: compact strip showing filename + Remove button
- Real per-page progress for PDF -> Markdown, with elapsed time and ETA.
- Threaded conversion so the UI stays responsive.
"""
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from converters.base import BaseConverter
from converters.registry import (
    CONVERTERS,
    get_converter,
    get_supported_inputs,
    get_supported_outputs,
)


# ---------- Stylesheets ----------
# Dark palette to fit Windows dark mode. Backgrounds are subtle dark
# tints rather than pure black so the zone is visible against the
# window background but doesn't burn the eyes.

_DROP_ZONE_EMPTY = """
    QFrame#dropZone {
        background-color: #1e2530;
        border: 3px dashed #5b6a82;
        border-radius: 10px;
    }
    QFrame#dropZone:hover {
        background-color: #243042;
        border-color: #60a5fa;
    }
"""

_DROP_ZONE_DRAG_OVER = """
    QFrame#dropZone {
        background-color: #1e3a5f;
        border: 4px dashed #60a5fa;
        border-radius: 10px;
    }
"""

_LOADED_STRIP = """
    QFrame#loadedStrip {
        background-color: #1e2a3f;
        border: 2px solid #3b82f6;
        border-radius: 10px;
    }
"""


def _set_mouse_transparent(widget: QWidget) -> None:
    """Make a widget pass mouse events through to its parent.

    Without this, clicking on the icon or headline label inside the
    drop zone gets swallowed by the label and never reaches the zone's
    mousePressEvent. This is the standard PyQt fix for clickable
    container widgets.
    """
    widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)


class DropZone(QFrame):
    """Embedded drop / click zone with two layouts swapped via QStackedWidget.

    Signals:
      - file_chosen(path): user picked a file (click or drop)
      - file_cleared(): user clicked Remove
      - multiple_files_dropped(kept_path): user dropped >1 file
    """

    file_chosen = pyqtSignal(Path)
    file_cleared = pyqtSignal()
    multiple_files_dropped = pyqtSignal(Path)

    # Indices into the QStackedWidget
    _PAGE_EMPTY = 0
    _PAGE_LOADED = 1

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setFrameShape(QFrame.Shape.NoFrame)  # we draw our own border via QSS
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(_DROP_ZONE_EMPTY)

        self._is_locked: bool = False
        self._has_file: bool = False

        self._build_ui()
        self._update_size()

    def _build_ui(self) -> None:
        # The zone is a QStackedWidget so we can swap whole pages
        # (empty vs loaded) cleanly without juggling visibility on
        # individual widgets.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget(self)
        _set_mouse_transparent(self._stack)
        outer.addWidget(self._stack)

        self._stack.addWidget(self._build_empty_page())
        self._stack.addWidget(self._build_loaded_page())
        self._stack.setCurrentIndex(self._PAGE_EMPTY)

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        _set_mouse_transparent(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 24, 20, 24)
        layout.addStretch()

        self._icon = QLabel("\u2B06")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setStyleSheet(
            "font-size: 56px; color: #60a5fa; "
            "background: transparent;"
        )
        _set_mouse_transparent(self._icon)
        layout.addWidget(self._icon)

        self._headline = QLabel("Drop a file here")
        self._headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._headline.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #f3f4f6; "
            "background: transparent;"
        )
        _set_mouse_transparent(self._headline)
        layout.addWidget(self._headline)

        self._subtitle = QLabel("or click to browse your files")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setStyleSheet(
            "color: #cbd5e1; font-size: 14px; "
            "background: transparent;"
        )
        _set_mouse_transparent(self._subtitle)
        layout.addWidget(self._subtitle)

        supported = ", ".join(f".{e}" for e in get_supported_inputs())
        self._types = QLabel(f"Supported: {supported}")
        self._types.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._types.setStyleSheet(
            "color: #94a3b8; font-size: 12px; margin-top: 8px; "
            "background: transparent;"
        )
        _set_mouse_transparent(self._types)
        layout.addWidget(self._types)

        layout.addStretch()
        return page

    def _build_loaded_page(self) -> QWidget:
        """Compact horizontal strip: [icon] [name + meta] [Remove]."""
        page = QWidget()
        _set_mouse_transparent(page)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(12)

        self._file_icon = QLabel("\U0001F4C4")
        self._file_icon.setStyleSheet(
            "font-size: 32px; background: transparent;"
        )
        _set_mouse_transparent(self._file_icon)
        layout.addWidget(self._file_icon)

        # Name + meta stacked vertically
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self._file_name = QLabel("")
        self._file_name.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #f3f4f6; "
            "background: transparent;"
        )
        _set_mouse_transparent(self._file_name)
        text_col.addWidget(self._file_name)

        self._file_meta = QLabel("")
        self._file_meta.setStyleSheet(
            "color: #cbd5e1; font-size: 12px; "
            "background: transparent;"
        )
        _set_mouse_transparent(self._file_meta)
        text_col.addWidget(self._file_meta)

        layout.addLayout(text_col, stretch=1)

        # Remove button -- this one MUST receive its own clicks, so it
        # is NOT mouse-transparent. A click on it fires _on_remove_clicked.
        # On hover it shifts to a red destructive style so the user
        # clearly understands it removes the file (and that the button
        # is interactive).
        # The objectName + #removeBtn selector is required: without it,
        # the parent QFrame's stylesheet cascades down and overrides
        # this button's :hover rule.
        self._remove_btn = QPushButton("\u2715 Remove")
        self._remove_btn.setObjectName("removeBtn")
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.setStyleSheet(
            "QPushButton#removeBtn { "
            "  background-color: #334155; "
            "  border: 1px solid #64748b; "
            "  color: #e2e8f0; "
            "  font-size: 12px; font-weight: 500; "
            "  padding: 6px 14px; "
            "  border-radius: 6px;"
            "} "
            "QPushButton#removeBtn:hover { "
            "  background-color: #dc2626; "
            "  border: 1px solid #ef4444; "
            "  color: #ffffff; "
            "} "
            "QPushButton#removeBtn:pressed { "
            "  background-color: #b91c1c; "
            "  border: 1px solid #dc2626; "
            "}"
        )
        self._remove_btn.clicked.connect(self._on_remove_clicked)
        layout.addWidget(self._remove_btn)

        return page

    # ---------- State transitions ----------
    def set_file(self, path: Path) -> None:
        self._has_file = True
        self._stack.setCurrentIndex(self._PAGE_LOADED)
        self.setStyleSheet(_LOADED_STRIP)
        # The frame's objectName is still "dropZone" so we need to
        # update the QSS to target the loaded state. Easier: change
        # objectName too so the right rule applies.
        self.setObjectName("loadedStrip")
        self.setStyleSheet(_LOADED_STRIP)
        self._update_size()

        self._file_name.setText(path.name)
        try:
            size_bytes = path.stat().st_size
            self._file_meta.setText(
                f"{path.suffix.upper().lstrip('.')} \u2022 "
                f"{_format_size(size_bytes)} \u2022 click to replace"
            )
        except OSError:
            self._file_meta.setText(
                f"{path.suffix.upper().lstrip('.')} \u2022 click to replace"
            )

    def clear_file(self) -> None:
        self._has_file = False
        self._stack.setCurrentIndex(self._PAGE_EMPTY)
        self.setObjectName("dropZone")
        self.setStyleSheet(_DROP_ZONE_EMPTY)
        self._headline.setText("Drop a file here")
        self._update_size()

    def set_locked(self, locked: bool) -> None:
        self._is_locked = locked
        self.setEnabled(not locked)
        if locked:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _update_size(self) -> None:
        """Adjust min/max height based on current page."""
        if self._has_file:
            self.setMinimumHeight(70)
            self.setMaximumHeight(80)
        else:
            self.setMinimumHeight(220)
            self.setMaximumHeight(280)

    # ---------- Event handlers ----------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._is_locked:
            super().mousePressEvent(event)
            return

        # If the click landed on the Remove button (which is a child
        # widget that handles its own clicks), let it handle it -- don't
        # also open the file picker, otherwise removing immediately
        # reopens the picker and makes the button look broken.
        # We map the event position from this widget's coords to the
        # Remove button's parent coords, then check if it's inside.
        if self._has_file:
            # Map our click to the Remove button's parent's coordinate
            # system, then check the button's geometry.
            btn_parent = self._remove_btn.parentWidget()
            if btn_parent is not None:
                pos_in_parent = btn_parent.mapFrom(self, event.pos())
                if self._remove_btn.geometry().contains(pos_in_parent):
                    # Forward the click manually so the button fires.
                    super().mousePressEvent(event)
                    self._on_remove_clicked()
                    return

        self._open_file_picker()
        super().mousePressEvent(event)

    def _on_remove_clicked(self) -> None:
        if self._is_locked:
            return
        self.clear_file()
        self.file_cleared.emit()

    def _open_file_picker(self) -> None:
        exts = sorted(get_supported_inputs())
        filter_str = (
            "Supported (" + " ".join(f"*.{e}" for e in exts) + ");;All Files (*.*)"
        )
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select File", "", filter_str
        )
        if path_str:
            self.file_chosen.emit(Path(path_str))

    # ---------- Drag and drop ----------
    def _supported_paths(self, event) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        supported_exts = set(get_supported_inputs())
        results: list[Path] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            p = Path(url.toLocalFile())
            if not p.is_file():
                continue
            if p.suffix.lstrip(".").lower() in supported_exts:
                results.append(p)
        return results

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._is_locked:
            event.ignore()
            return
        if self._supported_paths(event):
            event.acceptProposedAction()
            # Switch to drag-over visual regardless of current page.
            # Set objectName temporarily so the QSS rule applies.
            self.setObjectName("dropZone")
            self.setStyleSheet(_DROP_ZONE_DRAG_OVER)
            if not self._has_file:
                self._headline.setText("Release to upload")
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        # Restore whatever we were before the drag began.
        if self._has_file:
            self.setObjectName("loadedStrip")
            self.setStyleSheet(_LOADED_STRIP)
        else:
            self.setObjectName("dropZone")
            self.setStyleSheet(_DROP_ZONE_EMPTY)
            self._headline.setText("Drop a file here")
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        # Restore visual immediately. set_file() (called via the signal
        # handler in MainWindow) will apply the loaded look.
        if self._has_file:
            self.setObjectName("loadedStrip")
            self.setStyleSheet(_LOADED_STRIP)
        else:
            self.setObjectName("dropZone")
            self.setStyleSheet(_DROP_ZONE_EMPTY)
            self._headline.setText("Drop a file here")

        paths = self._supported_paths(event)
        if not paths:
            event.ignore()
            return

        event.acceptProposedAction()
        chosen = paths[0]
        self.file_chosen.emit(chosen)
        if len(paths) > 1:
            self.multiple_files_dropped.emit(chosen)


# ---------- Helpers ----------
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


def _format_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


# ---------- Worker thread ----------
class ConversionWorker(QThread):
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


# ---------- Main window ----------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("File Converter")
        self.setMinimumSize(560, 460)

        self._input_path: Optional[Path] = None
        self._worker: Optional[ConversionWorker] = None
        self._is_converting: bool = False

        self._start_time: Optional[float] = None
        self._last_progress: Optional[tuple[int, int]] = None

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(250)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        self.drop_zone = DropZone()
        self.drop_zone.file_chosen.connect(self._on_file_chosen)
        self.drop_zone.file_cleared.connect(self._on_file_cleared)
        self.drop_zone.multiple_files_dropped.connect(self._on_multiple_dropped)
        layout.addWidget(self.drop_zone)

        format_row = QHBoxLayout()
        label = QLabel("Convert to:")
        label.setStyleSheet("color: #f3f4f6; font-weight: 500;")
        format_row.addWidget(label)
        self.format_combo = QComboBox()
        self.format_combo.setEnabled(False)
        format_row.addWidget(self.format_combo, stretch=1)
        layout.addLayout(format_row)

        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setEnabled(False)
        self.convert_btn.setMinimumHeight(36)
        self.convert_btn.clicked.connect(self._on_convert)
        layout.addWidget(self.convert_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        timing_row = QHBoxLayout()
        self.elapsed_label = QLabel("")
        self.elapsed_label.setStyleSheet("color: #cbd5e1;")
        self.eta_label = QLabel("")
        self.eta_label.setStyleSheet("color: #94a3b8;")
        timing_row.addWidget(self.elapsed_label)
        timing_row.addStretch()
        timing_row.addWidget(self.eta_label)
        self.elapsed_label.setVisible(False)
        self.eta_label.setVisible(False)
        layout.addLayout(timing_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        supported = ", ".join(c.display_name for c in CONVERTERS)
        hint = QLabel(f"Conversions: {supported}")
        hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(hint)

        layout.addStretch()

    # ---------- Drop zone signal handlers ----------
    def _on_file_chosen(self, path: Path) -> None:
        self._input_path = path
        self.drop_zone.set_file(path)
        self._refresh_format_options()
        self._set_status("", color="")

    def _on_file_cleared(self) -> None:
        self._input_path = None
        self.format_combo.clear()
        self.format_combo.setEnabled(False)
        self.convert_btn.setEnabled(False)
        self._set_status("", color="")

    def _on_multiple_dropped(self, kept_path: Path) -> None:
        self._set_status(
            f"Multiple files dropped \u2014 using {kept_path.name}. "
            "Batch mode coming soon.",
            color="#fbbf24",
        )

    # ---------- Format dropdown ----------
    def _refresh_format_options(self) -> None:
        assert self._input_path is not None
        ext = self._input_path.suffix.lstrip(".").lower()
        outputs = get_supported_outputs(ext)

        self.format_combo.clear()
        if outputs:
            self.format_combo.addItems([o.upper() for o in outputs])
            self.format_combo.setEnabled(True)
            self.convert_btn.setEnabled(True)
        else:
            self.format_combo.setEnabled(False)
            self.convert_btn.setEnabled(False)
            QMessageBox.warning(
                self,
                "Unsupported format",
                f"No conversions are available for .{ext} files.",
            )

    # ---------- Convert flow ----------
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

        self._start_conversion(converter, self._input_path, Path(out_str))

    def _start_conversion(
        self,
        converter: BaseConverter,
        input_path: Path,
        output_path: Path,
    ) -> None:
        self._is_converting = True
        self.drop_zone.set_locked(True)
        self.convert_btn.setEnabled(False)
        self.format_combo.setEnabled(False)

        self.progress_bar.setVisible(True)
        self.elapsed_label.setVisible(True)
        self.eta_label.setVisible(True)
        self.eta_label.setText("")
        self._set_status("Converting\u2026", color="")

        if converter.supports_progress:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat("")

        self._start_time = time.monotonic()
        self._last_progress = None
        self.elapsed_label.setText("Elapsed: 0.0s")
        self._elapsed_timer.start()

        self._worker = ConversionWorker(converter, input_path, output_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_conversion_ok)
        self._worker.finished_err.connect(self._on_conversion_err)
        self._worker.start()

    # ---------- Progress / timer ----------
    def _on_progress(self, current: int, total: int) -> None:
        self._last_progress = (current, total)
        if total > 0:
            pct = int(round(current / total * 100))
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{current}/{total} pages  \u2014  %p%")

    def _tick_elapsed(self) -> None:
        if self._start_time is None:
            return
        elapsed = time.monotonic() - self._start_time
        self.elapsed_label.setText(f"Elapsed: {_format_duration(elapsed)}")

        if self._last_progress is not None:
            current, total = self._last_progress
            if 2 <= current < total:
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
        self._is_converting = False
        self.drop_zone.set_locked(False)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.elapsed_label.setVisible(False)
        self.eta_label.setVisible(False)
        self.convert_btn.setEnabled(True)
        self.format_combo.setEnabled(True)

        elapsed_str = (
            _format_duration(time.monotonic() - self._start_time)
            if self._start_time
            else "?"
        )
        self._set_status(
            f"\u2713 Saved to: {output_path}  (took {elapsed_str})",
            color="#4ade80",
        )

    def _on_conversion_err(self, message: str) -> None:
        self._stop_timing()
        self._is_converting = False
        self.drop_zone.set_locked(False)
        self.progress_bar.setVisible(False)
        self.elapsed_label.setVisible(False)
        self.eta_label.setVisible(False)
        self.convert_btn.setEnabled(True)
        self.format_combo.setEnabled(True)
        self._set_status(f"\u2717 {message}", color="#f87171")
        QMessageBox.critical(self, "Conversion failed", message)

    def _stop_timing(self) -> None:
        self._elapsed_timer.stop()

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};" if color else "")
