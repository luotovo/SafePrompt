from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path


attempts: list[str] = []
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


def report_failure(error_type, error, traceback):
    print(json.dumps({
        "status": "failed",
        "error_type": error_type.__name__,
        "error": str(error),
        "network_attempts": attempts,
    }, ensure_ascii=False))
    sys.__excepthook__(error_type, error, traceback)


sys.excepthook = report_failure

candidate, model_dir = sys.argv[1], Path(sys.argv[2]).resolve()
started = time.perf_counter()
if candidate == "uer":
    from safeprompt.adapters.uer import load_local

    recognizer = load_local(model_dir)
elif candidate == "uie":
    from safeprompt.adapters.paddle import load_uie_local

    recognizer = load_uie_local(model_dir)
elif candidate == "taskflow":
    from safeprompt.adapters.paddle import load_taskflow_local

    recognizer = load_taskflow_local(model_dir)
else:
    raise ValueError(f"unknown candidate: {candidate}")

results = recognizer.recognize("张三在北京大学工作。")
assert results, "recognizer returned no entities"
print(json.dumps({
    "candidate": candidate,
    "model_dir": str(model_dir),
    "elapsed_ms": (time.perf_counter() - started) * 1000,
    "network_attempts": attempts,
    "result_count": len(results),
}, ensure_ascii=False))
