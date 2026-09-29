# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


root = Path(SPEC).resolve().parent.parent
model_source = Path(os.environ["SAFEPROMPT_HYBRID_MODEL_DIR"]).resolve()
model_files = ("model.onnx", "vocab.txt", "tokenizer_config.json", "config.json")
missing = [name for name in model_files if not (model_source / name).is_file()]
if missing:
    raise FileNotFoundError(f"incomplete Hybrid model staging directory {model_source}: {missing}")

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(model_source / name), "models/uie-nano-onnx") for name in model_files],
    hiddenimports=["pynput.keyboard._win32", "release.hybrid_probe", "release.competition_portable_probe",
                   "release.competition_v2_probe"],
    runtime_hooks=[str(root / "release" / "runtime_hooks" / "pyi_rth_six_namespace.py")],
    excludes=[
        "paddle", "paddlenlp", "paddle2onnx", "torch", "tensorflow", "transformers",
        "tokenizers", "scipy", "ckip_transformers", "onnx", "onnxconverter_common",
    ],
    noarchive=False,
    optimize=0,
)
# Avoid collecting incompatible ICU DLLs from an ambient Poppler installation.
ambient_icu = {"icuuc.dll", "icudt78.dll"}
a.binaries = [item for item in a.binaries if item[0].lower() not in ambient_icu]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SafePrompt", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SafePrompt")
