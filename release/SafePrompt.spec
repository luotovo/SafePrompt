# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


root = Path(SPEC).resolve().parent.parent
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=["pynput.keyboard._win32"],
    hookspath=[str(root / "release" / "hooks")],
    hooksconfig={},
    runtime_hooks=[str(root / "release" / "runtime_hooks" / "pyi_rth_six_namespace.py")],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Qt 6 uses the Windows ICU shim from System32.  A developer PATH entry for
# Poppler can otherwise make PyInstaller collect its incompatible ICU 78 DLLs,
# causing QtCore to fail with "The specified procedure could not be found".
ambient_icu = {"icuuc.dll", "icudt78.dll"}
a.binaries = [item for item in a.binaries if item[0].lower() not in ambient_icu]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SafePrompt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SafePrompt",
)
