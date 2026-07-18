# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(repo_root / "windows_app" / "metatox_gui.py")],
    pathex=[str(repo_root / "windows_app")],
    binaries=[],
    datas=[
        (str(repo_root / "windows_app" / "README_WINDOWS.md"), "."),
        (str(repo_root / "Metatox.sh"), "."),
        (str(repo_root / "Scripts"), "Scripts"),
        (str(repo_root / "CondaEnv"), "CondaEnv"),
        (str(repo_root / "ExempleInput.txt"), "."),
    ],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name="MetaToxGUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MetaToxGUI",
)
