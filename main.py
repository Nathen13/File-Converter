"""File Converter - Windows desktop app for converting between document formats."""
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow


def _resource_path(relative: str) -> Path:
    """Resolve a path to a bundled resource.

    Works both in dev (when run from source) and in a PyInstaller-built
    .exe (when resources are unpacked to a temp directory exposed via
    sys._MEIPASS).
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def main() -> int:
    app = QApplication(sys.argv)

    # These names also drive QSettings storage (see gui/settings.py).
    # Keep them in sync.
    app.setOrganizationName("Nathen13")
    app.setApplicationName("File Converter")

    # Load the window/taskbar icon if it's available. The .ico file is
    # optional in dev (you'll just see the default Qt icon); the
    # PyInstaller build pulls it in via build.spec.
    icon_path = _resource_path("assets/icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
