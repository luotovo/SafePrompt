from __future__ import annotations

import json
import os
import threading
import time

from safeprompt.ner import NerService


class ControlledSlowRecognizer:
    def __init__(self, delay_seconds: float, finished: threading.Event):
        self.delay_seconds = delay_seconds
        self.finished = finished

    def recognize(self, text):
        deadline = time.perf_counter() + self.delay_seconds
        while time.perf_counter() < deadline:
            pass
        self.finished.set()
        return []


finished = threading.Event()
service = NerService(lambda: ControlledSlowRecognizer(2.5, finished), timeout_seconds=2.0)
cpu_before = time.process_time()
wall_before = time.perf_counter()
result = service.recognize("可控慢推理")
returned_at = time.perf_counter()
cpu_at_return = time.process_time()
thread_finished_at_return = finished.is_set()
finished.wait(timeout=5.0)
finished_at = time.perf_counter()
cpu_after = time.process_time()

print(json.dumps({
    "pid": os.getpid(),
    "result": result,
    "service_unavailable": service.unavailable,
    "caller_return_ms": (returned_at - wall_before) * 1000,
    "thread_finished_at_return": thread_finished_at_return,
    "background_finished": finished.is_set(),
    "background_finished_after_return_ms": (finished_at - returned_at) * 1000,
    "cpu_seconds_before_return": cpu_at_return - cpu_before,
    "cpu_seconds_after_return": cpu_after - cpu_at_return,
    "live_non_main_threads_after_wait": [
        thread.name for thread in threading.enumerate() if thread is not threading.main_thread()
    ],
}))
