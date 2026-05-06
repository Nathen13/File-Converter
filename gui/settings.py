"""Persistent app settings via QSettings.

QSettings stores key-value data in the platform-native location:
  - Windows: registry under HKCU\\Software\\Nathen13\\FileConverter
  - macOS: ~/Library/Preferences/com.nathen13.FileConverter.plist
  - Linux: ~/.config/Nathen13/FileConverter.conf

We wrap it in a small typed API so the rest of the code doesn't have
to touch QSettings directly. Right now it's just last-used folders;
future preferences (theme, default save format, etc.) slot in here.
"""
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSettings


# These names show up in the storage path (registry key on Windows).
# Change them only if you're prepared to migrate user data.
_ORG_NAME = "Nathen13"
_APP_NAME = "FileConverter"

# Setting keys
_KEY_LAST_OPEN_DIR = "paths/last_open_dir"
_KEY_LAST_SAVE_DIR = "paths/last_save_dir"


def _settings() -> QSettings:
    return QSettings(_ORG_NAME, _APP_NAME)


def _get_dir(key: str) -> str:
    """Return a stored directory path, validated to still exist.

    Returns "" (empty string) if the key isn't set or the directory
    no longer exists. QFileDialog accepts "" as "use platform default".
    """
    raw = _settings().value(key, "", type=str)
    if not raw:
        return ""
    if Path(raw).is_dir():
        return raw
    return ""


def get_last_open_dir() -> str:
    """Directory the user most recently opened a file from."""
    return _get_dir(_KEY_LAST_OPEN_DIR)


def get_last_save_dir() -> str:
    """Directory the user most recently saved a file to."""
    return _get_dir(_KEY_LAST_SAVE_DIR)


def set_last_open_dir(directory: str) -> None:
    if directory:
        _settings().setValue(_KEY_LAST_OPEN_DIR, directory)


def set_last_save_dir(directory: str) -> None:
    if directory:
        _settings().setValue(_KEY_LAST_SAVE_DIR, directory)


def remember_paths_from_open(path: Optional[str]) -> None:
    """Convenience: given a full file path the user just opened,
    record its parent directory."""
    if path:
        set_last_open_dir(str(Path(path).parent))


def remember_paths_from_save(path: Optional[str]) -> None:
    """Convenience: given a full file path the user just saved to,
    record its parent directory."""
    if path:
        set_last_save_dir(str(Path(path).parent))
