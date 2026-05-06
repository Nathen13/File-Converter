"""Main application window.

UI features:
- Embedded drop zone at the top of the window:
  * Empty state: large dashed-border prompt to drop or click
  * Loaded state: compact strip showing filename + Remove button
- Real per-page progress for PDF -> Markdown, with elapsed time and ETA.
- Cancel button for cancellable conversions.
- Threaded conversion so the UI stays responsive.
- "Show in Folder" affordance after successful conversion.
"""
import subprocess
import sys
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

from converters.base import BaseConverter, ConversionCancelled
from converters.registry import (
    CONVERTERS,
    get_converter,
    get_supported_inputs,
    get_supported_outputs,
)
from gui import settings


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
            self, "Select File", settings.get_last_open_dir(), filter_str
        )
        if path_str:
            settings.remember_paths_from_open(path_str)
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
        # Remember where dropped files came from too -- if the user
        # next opens the picker, it should land in the same folder.
        settings.remember_paths_from_open(str(chosen))
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


def _show_in_folder(path: Path) -> None:
    """Open the OS file manager with `path` selected.

    On Windows, `explorer /select,<path>` opens File Explorer with the
    file highlighted. The /select argument is finicky:
      - The path must use backslashes (forward slashes won't highlight)
      - It must be passed as a single shell-style argument, not a list,
        because Explorer parses /select,<path> as one combined token

    On macOS / Linux we fall back to opening the parent folder (no
    universal "select" equivalent).
    """
    try:
        if sys.platform == "win32":
            # Resolve symlinks and normalize to absolute Windows path
            # with backslashes -- /select is picky about both.
            normalized = str(path.resolve()).replace("/", "\\")
            # shell=False keeps things safer; we hand-build the command
            # string Explorer wants.
            subprocess.run(
                f'explorer /select,"{normalized}"',
                shell=False,
                # /select returns nonzero exit code even on success,
                # so we don't check it.
                check=False,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:  # Linux and other Unixes
            subprocess.Popen(["xdg-open", str(path.parent)])
    except (OSError, subprocess.SubprocessError):
        # If the OS file manager isn't available for some reason, just
        # silently fail. Not worth interrupting the user with a dialog
        # over a convenience feature.
        pass


# ---------- Worker thread ----------
class ConversionWorker(QThread):
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(str)
    finished_err = pyqtSignal(str)
    finished_cancelled = pyqtSignal()  # emitted when user cancelled

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
        # Cancellation flag, flipped by cancel() (called from UI thread).
        # _is_cancel_requested is read by _check_cancel from the worker
        # thread. Python's GIL makes a single bool read/write atomic, so
        # we don't need a Lock here.
        self._is_cancel_requested: bool = False

    def cancel(self) -> None:
        """Request cancellation. Called from the UI thread."""
        self._is_cancel_requested = True

    def _on_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)

    def _check_cancel(self) -> bool:
        return self._is_cancel_requested

    def _cleanup_partial_output(self) -> None:
        """Delete the output file if conversion didn't complete.

        Called when the user cancels mid-conversion. A half-extracted
        markdown file is generally useless; cleaner to start fresh.
        """
        try:
            if self._output_path.exists():
                self._output_path.unlink()
        except OSError:
            # If we can't delete it, that's not great but not worth
            # surfacing to the user -- they cancelled, the operation
            # is over from their perspective.
            pass

    def run(self) -> None:
        try:
            self._converter.convert(
                self._input_path,
                self._output_path,
                progress_callback=self._on_progress,
                cancel_check=self._check_cancel,
            )
            self.finished_ok.emit(str(self._output_path))
        except ConversionCancelled:
            self._cleanup_partial_output()
            self.finished_cancelled.emit()
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

        # Path of the most recent successful conversion output. Used
        # by the "Show in Folder" button. Reset when a new conversion
        # starts.
        self._last_output_path: Optional[Path] = None

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

        # Convert + Cancel buttons in a row. Cancel only appears
        # for converters that support it, and only while a conversion
        # is running.
        action_row = QHBoxLayout()
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setEnabled(False)
        self.convert_btn.setMinimumHeight(36)
        self.convert_btn.clicked.connect(self._on_convert)
        action_row.addWidget(self.convert_btn, stretch=1)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.setStyleSheet(
            "QPushButton { "
            "  background-color: #334155; "
            "  border: 1px solid #64748b; "
            "  color: #e2e8f0; "
            "  font-weight: 500; "
            "  padding: 6px 16px; "
            "  border-radius: 6px;"
            "} "
            "QPushButton:hover { "
            "  background-color: #dc2626; "
            "  border: 1px solid #ef4444; "
            "  color: #ffffff; "
            "} "
            "QPushButton:pressed { "
            "  background-color: #b91c1c; "
            "}"
        )
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setVisible(False)
        action_row.addWidget(self.cancel_btn)
        layout.addLayout(action_row)

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

        # Status label uses rich text so we can put a clickable link
        # to the output file in success messages. linkActivated fires
        # when the user clicks any <a href="..."> we put in there.
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        self.status_label.setOpenExternalLinks(False)
        self.status_label.linkActivated.connect(self._on_status_link_clicked)
        layout.addWidget(self.status_label)

        # "Show in Folder" button -- appears under the status line after
        # a successful conversion, hidden otherwise. Discoverable
        # complement to the clickable status link above (some users
        # won't notice the link is clickable).
        show_folder_row = QHBoxLayout()
        show_folder_row.addStretch()
        self.show_folder_btn = QPushButton("\U0001F4C2 Show in Folder")
        self.show_folder_btn.setObjectName("showFolderBtn")
        self.show_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show_folder_btn.setStyleSheet(
            "QPushButton#showFolderBtn { "
            "  background-color: #334155; "
            "  border: 1px solid #64748b; "
            "  color: #e2e8f0; "
            "  font-size: 12px; font-weight: 500; "
            "  padding: 6px 14px; "
            "  border-radius: 6px;"
            "} "
            "QPushButton#showFolderBtn:hover { "
            "  background-color: #1e3a5f; "
            "  border: 1px solid #3b82f6; "
            "  color: #ffffff; "
            "} "
            "QPushButton#showFolderBtn:pressed { "
            "  background-color: #1e293b; "
            "}"
        )
        self.show_folder_btn.clicked.connect(self._on_show_folder_clicked)
        self.show_folder_btn.setVisible(False)
        show_folder_row.addWidget(self.show_folder_btn)
        layout.addLayout(show_folder_row)

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

        # Default save location: last folder the user saved to (if any),
        # with the input file's stem and the new extension. If there's
        # no saved preference yet, fall back to the same folder as the
        # input file -- a reasonable default that keeps converted files
        # next to their source.
        default_dir = settings.get_last_save_dir() or str(self._input_path.parent)
        default_name = self._input_path.with_suffix(f".{output_ext}").name
        default_path = str(Path(default_dir) / default_name)

        out_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save As",
            default_path,
            f"{output_ext.upper()} (*.{output_ext})",
        )
        if not out_str:
            return

        settings.remember_paths_from_save(out_str)
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

        # Hide the Show in Folder button from any prior success --
        # otherwise the user could click it during a new conversion
        # and open the previous output folder, which is confusing.
        self.show_folder_btn.setVisible(False)
        self._last_output_path = None

        # Show the Cancel button only for converters that can actually
        # honor a cancel request. Showing a non-functional button would
        # mislead the user into thinking they could stop something they
        # can't.
        if converter.supports_cancel:
            self.cancel_btn.setVisible(True)
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText("Cancel")

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
        self._worker.finished_cancelled.connect(self._on_conversion_cancelled)
        self._worker.start()

    def _on_cancel(self) -> None:
        """Request cancellation of the running conversion.

        The worker checks the cancel flag between pages, so there's a
        short delay between clicking Cancel and the conversion actually
        stopping (typically <1 second per page).
        """
        if self._worker is None or not self._is_converting:
            return
        self._worker.cancel()
        # Give the user immediate feedback that we heard them, even
        # though the worker may still be finishing the current page.
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelling\u2026")
        self._set_status("Cancelling\u2026", color="#fbbf24")

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
    def _reset_ui_after_conversion(self) -> None:
        """Common cleanup for all three completion paths: ok, err, cancel."""
        self._stop_timing()
        self._is_converting = False
        self.drop_zone.set_locked(False)
        self.progress_bar.setVisible(False)
        self.elapsed_label.setVisible(False)
        self.eta_label.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.convert_btn.setEnabled(True)
        self.format_combo.setEnabled(True)

    def _on_conversion_ok(self, output_path: str) -> None:
        self.progress_bar.setValue(100)
        elapsed_str = (
            _format_duration(time.monotonic() - self._start_time)
            if self._start_time
            else "?"
        )
        self._reset_ui_after_conversion()

        # Stash the path so the Show in Folder button knows what to open.
        self._last_output_path = Path(output_path)

        # Status uses HTML so the file path becomes a clickable link.
        # We use a dummy "show:" scheme in href so linkActivated picks
        # it up but the OS doesn't try to launch it as a real URL.
        # The visible color is set via inline style since QLabel rich
        # text doesn't inherit from the parent stylesheet.
        import html as html_lib
        path_html = html_lib.escape(output_path)
        self._set_status(
            (
                f'<span style="color:#4ade80;">\u2713 Saved to: '
                f'<a href="show:{path_html}" '
                f'style="color:#4ade80; text-decoration: underline;">'
                f'{path_html}</a>'
                f'  (took {elapsed_str})'
                f'</span>'
            ),
            color="",
        )
        self.show_folder_btn.setVisible(True)

    def _on_conversion_err(self, message: str) -> None:
        self._reset_ui_after_conversion()
        self._last_output_path = None
        self.show_folder_btn.setVisible(False)
        self._set_status(f"\u2717 {message}", color="#f87171")
        QMessageBox.critical(self, "Conversion failed", message)

    def _on_conversion_cancelled(self) -> None:
        """User clicked Cancel and the worker stopped cleanly."""
        elapsed_str = (
            _format_duration(time.monotonic() - self._start_time)
            if self._start_time
            else "?"
        )
        self._reset_ui_after_conversion()
        self._last_output_path = None
        self.show_folder_btn.setVisible(False)
        self._set_status(
            f"\u26A0 Conversion cancelled after {elapsed_str}. "
            "Partial output discarded.",
            color="#fbbf24",
        )

    # ---------- Show in Folder ----------
    def _on_show_folder_clicked(self) -> None:
        if self._last_output_path is not None:
            _show_in_folder(self._last_output_path)

    def _on_status_link_clicked(self, href: str) -> None:
        """Handler for clicks on the rich-text link in the status label.

        We only respond to our internal "show:" scheme. Other links
        (e.g. real http URLs) are ignored, which is fine since we
        never insert any.
        """
        if href.startswith("show:"):
            path = Path(href[len("show:"):])
            _show_in_folder(path)

    def _stop_timing(self) -> None:
        self._elapsed_timer.stop()

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};" if color else "")
