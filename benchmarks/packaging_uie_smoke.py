from __future__ import annotations

import json
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import safeprompt.adapters.paddle as paddle_adapter


attempts: list[str] = []


@contextmanager
def deny_network_recording():
    original_socket = socket.socket
    original_create_connection = socket.create_connection

    class OfflineSocket(original_socket):
        def connect(self, address):
            attempts.append(repr(address))
            raise RuntimeError(f"network access blocked: {address!r}")

    def blocked_create_connection(address, *args, **kwargs):
        attempts.append(repr(address))
        raise RuntimeError(f"network access blocked: {address!r}")

    socket.socket = OfflineSocket
    socket.create_connection = blocked_create_connection
    try:
        yield
    finally:
        socket.socket = original_socket
        socket.create_connection = original_create_connection


def report_failure(error_type, error, traceback):
    print(json.dumps({
        "status": "failed",
        "error_type": error_type.__name__,
        "error": str(error),
        "network_attempts": attempts,
    }, ensure_ascii=False))
    sys.__excepthook__(error_type, error, traceback)


sys.excepthook = report_failure
paddle_adapter.deny_network = deny_network_recording

model_arg = Path(sys.argv[1])
model_base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
model_dir = (model_arg if model_arg.is_absolute() else model_base / model_arg).resolve()
required_files = (
    "config.json",
    "vocab.txt",
    "special_tokens_map.json",
    "tokenizer_config.json",
)
missing_files = [name for name in required_files if not (model_dir / name).is_file()]
model_pairs = [
    model_file.stem
    for model_file in model_dir.glob("*.pdmodel")
    if (model_dir / f"{model_file.stem}.pdiparams").is_file()
] if model_dir.is_dir() else []
if missing_files or not model_pairs:
    raise FileNotFoundError(
        f"incomplete local UIE static model at {model_dir}; "
        f"missing={missing_files}, model_parameter_pairs={model_pairs}"
    )

from paddlenlp.taskflow import utils as taskflow_utils

taskflow_utils.DOWNLOAD_CHECK = True
text = sys.argv[2] if len(sys.argv) > 2 else "韩静在海川大学提交了报告。"
started = time.perf_counter()
recognizer = paddle_adapter.load_uie_local(model_dir)
results = recognizer.recognize(text)
print(json.dumps({
    "status": "ok",
    "model_dir": str(model_dir),
    "text": text,
    "elapsed_ms": (time.perf_counter() - started) * 1000,
    "network_attempts": attempts,
    "entities": [
        {
            "category": result.category,
            "text": result.text,
            "start": result.start,
            "end": result.end,
            "confidence": result.confidence,
        }
        for result in results
    ],
}, ensure_ascii=False))
