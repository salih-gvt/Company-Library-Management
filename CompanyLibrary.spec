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
    # email_reminders.py is bundled as a plain data file (like app.py/
    # database.py), so PyInstaller's static analysis never sees its
    # imports - smtplib/email.* have to be hinted explicitly or they're
    # silently left out of the frozen build.
    + collect_submodules("email")
    + ["smtplib", "ssl"]
)

a = Analysis(
    ["source/launcher.py"],
    pathex=[],
    binaries=[],
    datas=streamlit_datas + altair_datas + webview_datas + [
        ("source/app.py", "."),
        ("source/database.py", "."),
        ("source/version.py", "."),
        ("source/email_reminders.py", "."),
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
