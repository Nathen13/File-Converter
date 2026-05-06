# PyInstaller spec for File Converter
# Build with:  pyinstaller build.spec
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# pymupdf ships with non-Python resource files (YAML configs, ONNX models
# for layout detection) that PyInstaller's static analysis misses. We
# collect them explicitly so they end up next to the frozen Python code.
datas = []
datas += collect_data_files('pymupdf')
datas += collect_data_files('pymupdf4llm')

# Same idea for hidden imports - libraries that get loaded dynamically
# at runtime won't be detected by static analysis.
hiddenimports = [
    'pymupdf4llm',
    'pymupdf',
    'docx2pdf',
    'win32com',
    'win32com.client',
    'pythoncom',
]
hiddenimports += collect_submodules('pymupdf')


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
    console=False,        # GUI app -> no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='app.ico',     # uncomment when you add an icon
)
