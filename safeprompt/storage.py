from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

from .core import DEFAULT_SELECTED, KNOWN_CATEGORIES


DATA_DIR = Path(os.environ["LOCALAPPDATA"]) / "SafePrompt"
SETTINGS_FILE = DATA_DIR / "settings.bin"
CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _protect(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "SafePrompt", None, None, None,
                                                   CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _unprotect(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None,
                                                     CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def default_settings() -> dict:
    return {"dictionary": [], "hotkey": "<ctrl>+<shift>+s", "high_risk_warning": True,
            "category_defaults": DEFAULT_SELECTED.copy(), "startup": False}


def _valid_dictionary(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)
            and isinstance(item.get("term"), str) and bool(item["term"].strip())
            and item.get("category") in KNOWN_CATEGORIES
            and isinstance(item.get("default_selected"), bool)]


def _valid_category_defaults(value: object) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {key: selected for key, selected in value.items()
            if key in KNOWN_CATEGORIES and isinstance(selected, bool)}


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return default_settings()
    try:
        loaded = json.loads(_unprotect(SETTINGS_FILE.read_bytes()).decode("utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("settings root must be an object")
        defaults = default_settings()
        validators = {"hotkey": lambda value: isinstance(value, str) and bool(value),
                      "high_risk_warning": lambda value: isinstance(value, bool), "category_defaults": lambda value: isinstance(value, dict),
                      "startup": lambda value: isinstance(value, bool)}
        result = defaults | {key: loaded[key] for key, valid in validators.items() if key in loaded and valid(loaded[key])}
        result["dictionary"] = _valid_dictionary(loaded.get("dictionary"))
        result["category_defaults"] = defaults["category_defaults"] | _valid_category_defaults(loaded.get("category_defaults"))
        return result
    except (OSError, ValueError, json.JSONDecodeError):
        corrupt = SETTINGS_FILE.with_suffix(".corrupt")
        index = 1
        while corrupt.exists():
            corrupt = SETTINGS_FILE.with_suffix(f".corrupt.{index}")
            index += 1
        SETTINGS_FILE.replace(corrupt)
        return default_settings()


def save_settings(settings: dict) -> None:
    """Persist only user-configured settings and dictionary entries, encrypted for this Windows user."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS_FILE.with_suffix(".tmp")
    temporary.write_bytes(_protect(json.dumps(settings, ensure_ascii=False).encode("utf-8")))
    temporary.replace(SETTINGS_FILE)
