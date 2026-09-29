"""Classify a frozen Hybrid artifact and report its largest files."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


CATEGORIES = (
    "UIE ONNX Model", "UIE tokenizer/config assets", "ONNX Runtime", "NumPy",
    "Python Runtime", "PySide6 / Qt", "Project Code / Resources", "Other Python Packages",
    "Other Native DLL", "Metadata / Misc", "Unknown",
)


def classify(relative: Path) -> str:
    value = relative.as_posix().lower()
    name = relative.name.lower()
    if value.endswith("models/uie-nano-onnx/model.onnx"):
        return "UIE ONNX Model"
    if "/models/uie-nano-onnx/" in f"/{value}":
        return "UIE tokenizer/config assets"
    if "onnxruntime" in value:
        return "ONNX Runtime"
    if "/numpy" in f"/{value}" or "numpy.libs" in value:
        return "NumPy"
    if "pyside6" in value or "shiboken6" in value or "/qt" in f"/{value}":
        return "PySide6 / Qt"
    if name == "safeprompt.exe":
        return "Project Code / Resources"
    if (name == "python312.dll" or name == "base_library.zip" or value.startswith("_internal/python")
            or (value.startswith("_internal/") and name.startswith("_") and name.endswith(".pyd"))):
        return "Python Runtime"
    if any(package in value for package in ("coloredlogs", "flatbuffers", "humanfriendly", "mpmath",
                                             "packaging", "protobuf", "pyreadline", "sympy", "pynput", "six")):
        return "Other Python Packages"
    if relative.suffix.lower() in {".dll", ".pyd"}:
        return "Other Native DLL"
    if any(part.lower().endswith((".dist-info", ".egg-info")) for part in relative.parts):
        return "Metadata / Misc"
    if relative.suffix.lower() in {".py", ".pyc", ".zip", ".json", ".txt", ".md", ".dat"}:
        return "Metadata / Misc"
    return "Unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact.resolve()
    files = [path for path in root.rglob("*") if path.is_file()]
    rows = []
    totals = defaultdict(lambda: {"file_count": 0, "bytes": 0})
    for path in files:
        relative = path.relative_to(root)
        category = classify(relative)
        size = path.stat().st_size
        totals[category]["file_count"] += 1
        totals[category]["bytes"] += size
        rows.append({"path": relative.as_posix(), "bytes": size, "category": category})
    total_bytes = sum(row["bytes"] for row in rows)
    categories = {}
    for category in CATEGORIES:
        item = totals[category]
        categories[category] = {**item, "mib": item["bytes"] / 1048576,
                                "percent": item["bytes"] * 100 / total_bytes if total_bytes else 0}
    top = []
    for row in sorted(rows, key=lambda item: item["bytes"], reverse=True)[:50]:
        necessary = row["category"] not in {"Metadata / Misc", "Unknown"}
        top.append({**row, "mib": row["bytes"] / 1048576, "necessary": necessary,
                    "possible_trim_candidate": row["category"] in {"Metadata / Misc", "Unknown"}})
    payload = {"artifact": str(root), "file_count": len(rows), "bytes": total_bytes,
               "mib": total_bytes / 1048576, "categories": categories, "top_50": top}
    args.output.resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("file_count", "bytes", "mib")}, indent=2))


if __name__ == "__main__":
    main()
