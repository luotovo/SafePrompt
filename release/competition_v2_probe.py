"""Black-box regression and repeatability probe executed by the frozen application."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDialog

import safeprompt.app as app_module
from safeprompt.core import mask


def _actual(findings) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {}
    for finding in findings:
        values.setdefault(finding.category, set()).add(finding.original_value)
    return values


def _case_pass(case: dict, findings) -> bool:
    actual = _actual(findings)
    for category, expected_values in case.get("expected", {}).items():
        if category == "ORG":
            if not all(any(expected in value or value in expected for value in actual.get(category, set()))
                       for expected in expected_values):
                return False
        elif not set(expected_values) <= actual.get(category, set()):
            return False
    if case.get("require_org") and not actual.get("ORG"):
        return False
    if set(case.get("forbidden_person_values", [])) & actual.get("PERSON", set()):
        return False
    return all(not actual.get(category) for category in case.get("forbidden", []))


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--competition-v2-probe", action="store_true")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warm-repeat", type=int, default=20)
    parser.add_argument("--long-repeat", type=int, default=5)
    args = parser.parse_args()
    corpus = json.loads(args.input.resolve().read_text(encoding="utf-8"))
    first = next(case for case in corpus if case["id"] == "person-21")
    ordered = [first, *(case for case in corpus if case is not first)]

    app = QApplication.instance() or QApplication([])
    clipboard = app.clipboard()
    previous_clipboard = clipboard.text()
    controller = app_module.SafePromptApp(app)
    captured = []
    original_exec = app_module.PreviewDialog.exec

    def capture(dialog):
        safe, resolved = mask(dialog.text, dialog.findings)
        controller.create_recovery(resolved)
        captured.append({"text": dialog.text, "findings": dialog.findings,
                         "recovery_exact": controller.recovery.restore(safe).text == dialog.text})
        return QDialog.DialogCode.Accepted

    def process(text: str, timeout: float = 120.0) -> tuple[list, bool, dict]:
        before = len(captured)
        previous_request = controller.detection_generation
        clipboard.setText(text)
        controller.process_clipboard()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            diagnostics = controller.last_detection_diagnostics
            if diagnostics.get("request_id", 0) > previous_request:
                app.processEvents()
                row = captured[-1] if len(captured) > before and captured[-1]["text"] == text else None
                return (row["findings"] if row else [], row["recovery_exact"] if row else True,
                        dict(diagnostics))
            time.sleep(0.01)
        return [], False, {"error": "timeout"}

    rows = []
    warm_passes = 0
    long_passes = 0
    try:
        app_module.PreviewDialog.exec = capture
        for case in ordered:
            findings, recovered, diagnostics = process(case["text"])
            passed = _case_pass(case, findings) and recovered
            rows.append({"id": case["id"], "pass": passed,
                         "categories": sorted(_actual(findings)), "diagnostics": diagnostics})
        sequence = ordered[:]
        for index in range(args.warm_repeat):
            case = sequence[index % len(sequence)]
            findings, recovered, _ = process(case["text"])
            warm_passes += int(_case_pass(case, findings) and recovered)
        long_text = "\n".join(case["text"] for case in ordered)
        long_expected_people = {value for case in ordered for value in case.get("expected", {}).get("PERSON", [])}
        for _ in range(args.long_repeat):
            findings, recovered, _ = process(long_text)
            people = _actual(findings).get("PERSON", set())
            long_passes += int(long_expected_people <= people and recovered)
    finally:
        app_module.PreviewDialog.exec = original_exec
        controller.stop_listener()
        clipboard.setText(previous_clipboard)
        QCoreApplication.processEvents()

    payload = {
        "backend_state": controller.ner.state if controller.ner is not None else "UNAVAILABLE",
        "manual_cases": len(rows),
        "manual_passes": sum(row["pass"] for row in rows),
        "first_request_pass": rows[0]["pass"],
        "warm_repeat": f"{warm_passes}/{args.warm_repeat}",
        "long_repeat": f"{long_passes}/{args.long_repeat}",
        "rows": rows,
    }
    args.output.resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if (payload["manual_passes"] == payload["manual_cases"] and payload["first_request_pass"]
                 and warm_passes == args.warm_repeat and long_passes == args.long_repeat) else 1


if __name__ == "__main__":
    raise SystemExit(run())
