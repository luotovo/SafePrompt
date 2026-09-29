"""Frozen Hybrid probe driven by an external capability corpus."""

from __future__ import annotations

import argparse
import ctypes
import json
import socket
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

import numpy as np

import safeprompt.adapters.onnx_uie as onnx_adapter
import safeprompt.app as app_module
from safeprompt.core import detect, mask
from safeprompt.ner import to_findings
from safeprompt.recovery import ActiveRecoverySession


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def _rss_bytes() -> int:
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    get_current_process = ctypes.windll.kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ProcessMemoryCounters), ctypes.c_ulong]
    get_memory_info.restype = ctypes.c_int
    handle = get_current_process()
    if not get_memory_info(handle, ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return int(counters.WorkingSetSize)


@contextmanager
def recording_network_guard(attempts: list[str]):
    original_socket, original_create_connection = socket.socket, socket.create_connection

    class OfflineSocket(original_socket):
        def connect(self, address):
            attempts.append(repr(address))
            raise RuntimeError(f"network access blocked during Hybrid probe: {address!r}")

    def blocked_create_connection(address, *args, **kwargs):
        attempts.append(repr(address))
        raise RuntimeError(f"network access blocked during Hybrid probe: {address!r}")

    socket.socket, socket.create_connection = OfflineSocket, blocked_create_connection
    try:
        yield
    finally:
        socket.socket, socket.create_connection = original_socket, original_create_connection


def _metrics(expected: set, actual: set) -> dict:
    tp, fp, fn = len(expected & actual), len(actual - expected), len(expected - actual)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def _pipeline(recognizer, text: str, defaults: dict[str, bool] | None = None) -> tuple[list, str, bool]:
    findings = detect(text, category_defaults=defaults,
                      extra_candidates=to_findings(text, recognizer.recognize(text), defaults))
    safe, resolved = mask(text, findings)
    recovery = ActiveRecoverySession()
    recovery.replace(resolved)
    return findings, safe, recovery.restore(safe).text == text


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hybrid-probe", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--startup-only", action="store_true")
    parser.add_argument("--failure-probe", action="store_true")
    args = parser.parse_args()
    if args.startup_only:
        args.output.resolve().write_text(json.dumps({"startup_ready": True, "rss_bytes": _rss_bytes()}),
                                         encoding="utf-8")
        return 0
    if args.failure_probe:
        error = None
        try:
            onnx_adapter.load_onnx_uie_local(app_module.uie_model_dir())
        except Exception as caught:
            error = f"{type(caught).__name__}: {caught}"
        degraded = mask("10.0.0.1 测试客户", detect(
            "10.0.0.1 测试客户", [("测试客户", "CUSTOMER", True)]))[0]
        payload = {"backend_unavailable": error is not None, "error": error,
                   "degraded_safe": degraded, "rule_dictionary_ok": degraded == "<IP_1> <CUSTOMER_1>"}
        args.output.resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if payload["backend_unavailable"] and payload["rule_dictionary_ok"] else 1
    if args.input is None:
        parser.error("--input is required unless --startup-only or --failure-probe is used")
    rows = json.loads(args.input.resolve().read_text(encoding="utf-8"))
    attempts: list[str] = []
    onnx_adapter.deny_network = lambda: recording_network_guard(attempts)

    lazy_service = app_module.NerService(lambda: None)
    lazy_before_use = lazy_service._recognizer is None and not lazy_service.loading
    rss_before_model = _rss_bytes()
    load_started = time.perf_counter()
    recognizer = onnx_adapter.load_onnx_uie_local(app_module.uie_model_dir())
    cold_load_ms = (time.perf_counter() - load_started) * 1000
    ort_loaded = recognizer.session is not None
    numpy_ok = np.asarray([1], dtype=np.int64).dtype == np.int64
    rss_after_model = _rss_bytes()

    gold, predicted = defaultdict(set), defaultdict(set)
    recovery_exact = 0
    inference_times = []
    for row_index, row in enumerate(rows):
        for entity in row["entities"]:
            if entity["category"] in {"PERSON", "ORG"}:
                gold[entity["category"]].add((row_index, entity["start"], entity["end"], entity["text"]))
        started = time.perf_counter()
        findings, _, recovered = _pipeline(recognizer, row["text"])
        inference_times.append((time.perf_counter() - started) * 1000)
        recovery_exact += recovered
        for finding in findings:
            if finding.category in {"PERSON", "ORG"}:
                predicted[finding.category].add(
                    (row_index, finding.start, finding.end, finding.original_value))

    person_text = "负责人张安联系了周明。"
    _, person_off, _ = _pipeline(recognizer, person_text, {"PERSON": False, "ORG": True})
    org_text = "腾讯科技有限公司提交了材料。"
    _, org_off, _ = _pipeline(recognizer, org_text, {"PERSON": True, "ORG": False})
    both_disabled_no_load = not app_module.entity_model_enabled({"PERSON": False, "ORG": False})
    collision = "<PERSON_1> <ORG_1> 周明联系腾讯科技有限公司。"
    _, collision_safe, collision_recovery = _pipeline(recognizer, collision)
    ordered = sorted(inference_times)
    rss_after_samples = _rss_bytes()
    payload = {
        "model_dir": str(app_module.uie_model_dir()),
        "lazy_before_use": lazy_before_use,
        "ort_loaded": ort_loaded,
        "numpy_ok": numpy_ok,
        "network_attempts": attempts,
        "cold_load_ms": cold_load_ms,
        "rss_bytes": {"before_model": rss_before_model, "after_model": rss_after_model,
                      "after_samples": rss_after_samples},
        "warm_inference_ms": {
            "median": ordered[len(ordered) // 2],
            "p95": ordered[max(0, int(len(ordered) * 0.95) - 1)],
        },
        "metrics": {category: _metrics(gold[category], predicted[category])
                    for category in ("PERSON", "ORG")},
        "recovery_exact": recovery_exact,
        "samples": len(rows),
        "category_control": {
            "person_disabled": "<PERSON_" not in person_off,
            "org_disabled": "<ORG_" not in org_off,
            "both_disabled_no_load": both_disabled_no_load,
        },
        "placeholder_collision": (collision_safe.startswith("<PERSON_1> <ORG_1> <PERSON_2>")
                                  and "<ORG_2>" in collision_safe and collision_recovery),
    }
    args.output.resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    checks = [lazy_before_use, ort_loaded, numpy_ok, not attempts, recovery_exact == len(rows),
              payload["placeholder_collision"], *payload["category_control"].values()]
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(run())
