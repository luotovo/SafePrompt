"""Generate a factual, file-level inventory for a frozen SafePrompt artifact.

This tool records hashes, PE metadata and deterministic source-package/category
mappings.  It deliberately does not make legal-compliance decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MODEL_NAMES = {"model.onnx", "vocab.txt", "tokenizer_config.json", "config.json"}
PYTHON_NATIVE = {
    "python3.dll", "python312.dll", "base_library.zip", "libffi-8.dll",
    "_asyncio.pyd", "_bz2.pyd", "_ctypes.pyd", "_decimal.pyd", "_hashlib.pyd",
    "_lzma.pyd", "_multiprocessing.pyd", "_overlapped.pyd", "_queue.pyd",
    "_socket.pyd", "_ssl.pyd", "_wmi.pyd", "pyexpat.pyd", "select.pyd", "unicodedata.pyd",
}
AMBIENT_POPPLER = {"libcrypto-3-x64.dll", "libssl-3-x64.dll"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pe_metadata(path: Path) -> dict[str, str]:
    if path.suffix.casefold() not in {".dll", ".exe", ".pyd"}:
        return {}
    try:
        import pefile
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        values = {}
        for file_info in getattr(pe, "FileInfo", ()):
            for entry in file_info:
                if getattr(entry, "Key", b"") == b"StringFileInfo":
                    for table in entry.StringTable:
                        values.update({key.decode(errors="replace"): value.decode(errors="replace")
                                       for key, value in table.entries.items()})
        return {name: values.get(name, "") for name in ("FileVersion", "ProductName", "CompanyName")}
    except Exception:
        return {"FileVersion": "", "ProductName": "", "CompanyName": ""}


def _classify(relative: str) -> tuple[str, str]:
    normalized = relative.replace("\\", "/")
    lower, name = normalized.casefold(), Path(normalized).name.casefold()
    if "/models/uie-nano-onnx/" in f"/{lower}" and name in MODEL_NAMES:
        return (("Model", "UIE Nano / locally converted ONNX") if name == "model.onnx"
                else ("Tokenizer Asset", "PaddleNLP UIE asset"))
    if lower.startswith("_internal/onnxruntime/"):
        return "ONNX Runtime", "onnxruntime 1.22.1 wheel"
    if lower.startswith("_internal/numpy"):
        source = "NumPy 2.5.3 wheel"
        if "libscipy_openblas" in lower:
            source = "NumPy 2.5.3 wheel bundled scipy-openblas/OpenBLAS runtime"
        return "NumPy", source
    if lower.startswith("_internal/pyside6/"):
        if name in {"msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll"}:
            return "MSVC Runtime", "PySide6 6.11.2 wheel"
        return "Qt/PySide", "PySide6 6.11.2 wheels"
    if lower.startswith("_internal/shiboken6/"):
        if name.startswith(("msvcp", "vcruntime")):
            return "MSVC Runtime", "shiboken6 6.11.2 wheel"
        return "Qt/PySide", "shiboken6 6.11.2 wheel"
    if name == "shiboken6.abi3.dll":
        return "Qt/PySide", "shiboken6 6.11.2 wheel"
    if name in {"libcrypto-3.dll", "libssl-3.dll"}:
        return "OpenSSL", "CPython 3.12.0 Windows installation"
    if name in AMBIENT_POPPLER:
        return "OpenSSL", "ambient Codex Poppler runtime (host PATH contamination)"
    if name in {"msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"}:
        return "MSVC Runtime", "source must be established from controlled-build TOC"
    if name.startswith("api-ms-win-crt-") or name.startswith("api-ms-win-core-"):
        return "Windows Runtime", "source must be established from controlled-build TOC"
    if name in PYTHON_NATIVE:
        return "Python Runtime", "CPython 3.12.0 Windows installation"
    if lower.startswith("_internal/pyreadline3-"):
        return "Python Package", "pyreadline3 3.5.6 wheel"
    if lower == "safeprompt.exe":
        return "Project", "SafePrompt plus PyInstaller 6.22.3 bootloader/PYZ"
    if Path(normalized).suffix.casefold() in {".dll", ".pyd"}:
        return "Other Native DLL", "unresolved by deterministic mapping"
    return "Other Third Party", "unresolved by deterministic mapping"


def build_inventory(artifact: Path) -> dict:
    artifact = artifact.resolve()
    if not artifact.is_dir():
        raise FileNotFoundError(f"artifact directory not found: {artifact}")
    files = []
    for path in sorted((item for item in artifact.rglob("*") if item.is_file()),
                       key=lambda item: item.relative_to(artifact).as_posix().casefold()):
        relative = path.relative_to(artifact).as_posix()
        category, source_package = _classify(relative)
        files.append({
            "path": relative,
            "filename": path.name,
            "size": path.stat().st_size,
            "sha256": _sha256(path),
            **_pe_metadata(path),
            "source_package": source_package,
            "category": category,
        })
    categories = {}
    for item in files:
        bucket = categories.setdefault(item["category"], {"files": 0, "bytes": 0})
        bucket["files"] += 1
        bucket["bytes"] += item["size"]
    return {"artifact": str(artifact), "file_count": len(files),
            "total_bytes": sum(item["size"] for item in files),
            "categories": categories, "files": files}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_inventory(args.artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("artifact", "file_count", "total_bytes", "categories")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
