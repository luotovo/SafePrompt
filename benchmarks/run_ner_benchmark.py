from __future__ import annotations

import argparse
import ctypes
import importlib
import importlib.metadata
import json
import math
import platform
import statistics
import time
from pathlib import Path

try:
    from .ner_dataset import samples
except ImportError:
    from ner_dataset import samples


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def rss_bytes() -> int:
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    get_current_process = ctypes.windll.kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    process = get_current_process()
    get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
    if not get_process_memory_info(process, ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.WorkingSetSize


def load_factory(spec: str):
    module, name = spec.split(":", 1)
    return getattr(importlib.import_module(module), name)


def score(recognizer, repeats: int) -> dict:
    rows = samples()
    gold = {category: set() for category in ("PERSON", "ORG")}
    predicted = {category: set() for category in ("PERSON", "ORG")}
    latencies = []
    long_latencies = []
    for index, row in enumerate(rows):
        for entity in row["entities"]:
            gold[entity["category"]].add((index, entity["start"], entity["end"], entity["text"]))
        # Accuracy uses one fixed prediction; timing runs are deliberately separate.
        results = recognizer.recognize(row["text"])
        timings = []
        for _ in range(repeats):
            started = time.perf_counter()
            recognizer.recognize(row["text"])
            timings.append((time.perf_counter() - started) * 1000)
        if len(row["text"]) >= 1000:
            long_latencies.extend(timings)
        else:
            latencies.extend(timings)
        for entity in results:
            if entity.category in predicted:
                predicted[entity.category].add((index, entity.start, entity.end, entity.text))
    metrics = {}
    total_fp = 0
    for category in ("PERSON", "ORG"):
        tp = len(gold[category] & predicted[category])
        fp = len(predicted[category] - gold[category])
        fn = len(gold[category] - predicted[category])
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        metrics[category] = {"precision": precision, "recall": recall,
                             "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}
        total_fp += fp
    ordered = sorted(latencies)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    ordered_long = sorted(long_latencies)
    long_p95 = (ordered_long[max(0, math.ceil(len(ordered_long) * 0.95) - 1)]
                if ordered_long else None)
    return {"metrics": metrics, "false_positives": total_fp,
            "median_latency_ms": statistics.median(latencies), "p95_latency_ms": p95,
            "max_latency_ms": max(latencies),
            "long_text_latency_ms": statistics.median(long_latencies) if long_latencies else None,
            "long_text_p95_latency_ms": long_p95,
            "long_text_max_latency_ms": max(long_latencies) if long_latencies else None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("factory", help="module:function returning an already local/offline recognizer")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    rss_before = rss_bytes()
    started = time.perf_counter()
    recognizer = load_factory(args.factory)(args.model_dir)
    load_ms = (time.perf_counter() - started) * 1000
    recognizer.recognize(samples()[0]["text"])
    rss_after = rss_bytes()
    result = score(recognizer, args.repeats)
    result.update({"cold_load_ms": load_ms,
                   "model_directory_bytes": sum(path.stat().st_size for path in args.model_dir.rglob("*") if path.is_file()),
                   "rss_delta_bytes": max(0, rss_after - rss_before), "pyinstaller_added_bytes": None,
                   "windows_runtime_issues": [], "offline_startup": None, "hidden_downloads": None})
    packages = {}
    for package in ("torch", "transformers", "paddlepaddle", "paddlenlp"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    result["environment"] = {"python": platform.python_version(), "platform": platform.platform(),
                             "packages": packages}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
