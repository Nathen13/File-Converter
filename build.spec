# PyInstaller spec for File Converter
# Build with:  pyinstaller build.spec
# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Bundle pymupdf's data files (yaml configs, ONNX models for layout
# detection) so they're available at runtime in the frozen .exe.
datas = []
datas += collect_data_files('pymupdf')
datas += collect_data_files('pymupdf4llm')

# Bundle the assets folder (app icon, etc.) into the .exe. The
# (source, dest) tuple says "copy ./assets into the bundle at the
# 'assets' subdirectory."
if os.path.isdir('assets'):
    datas.append(('assets', 'assets'))

# Hidden imports for libraries that get loaded dynamically and aren't
# detected by static analysis.
hiddenimports = [
    'pymupdf4llm',
    'pymupdf',
    'docx2pdf',
    'win32com',
    'win32com.client',
    'pythoncom',
]
hiddenimports += collect_submodules('pymupdf')

# Path to the .exe icon. PyInstaller embeds this so the file shows
# the right icon in File Explorer and the Start menu, separate from
# the runtime QApplication.setWindowIcon() call.
icon_path = 'assets/icon.ico' if os.path.exists('assets/icon.ico') else None


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FileConverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
