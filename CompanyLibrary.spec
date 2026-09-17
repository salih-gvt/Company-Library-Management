# PyInstaller spec for Company Library Management.
#
# Build with:
#   .venv\Scripts\pyinstaller.exe CompanyLibrary.spec --noconfirm
#
# Output lands in dist\Company Library Management\.

import streamlit
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

block_cipher = None

streamlit_datas = collect_data_files("streamlit") + copy_metadata("streamlit")
altair_datas = collect_data_files("altair") + copy_metadata("altair")
webview_datas = collect_data_files("webview") + copy_metadata("pywebview")

hidden_imports = (
    collect_submodules("streamlit")
    + collect_submodules("altair")
    + collect_submodules("webview")
    + collect_submodules("clr_loader")
)

a = Analysis(
    ["source/launcher.py"],
    pathex=[],
    binaries=[],
    datas=streamlit_datas + altair_datas + webview_datas + [
        ("source/app.py", "."),
        ("source/database.py", "."),
        ("source/version.py", "."),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Company Library",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Company Library Management",
)
