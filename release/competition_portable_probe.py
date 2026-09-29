"""End-to-end smoke probe executed from the frozen competition portable."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from safeprompt.adapters.onnx_uie import load_onnx_uie_local
from safeprompt.app import uie_model_dir
from safeprompt.core import detect, mask
from safeprompt.ner import to_findings
from safeprompt.recovery import ActiveRecoverySession


CASES = [
    ("person-org", "张伟代表星河科技有限公司参加评审。", {"PERSON", "ORG"}),
    ("phone-email", "李娜电话13800138000，邮箱lina@example.com。", {"PERSON", "PHONE", "EMAIL"}),
    ("credentials", "password=DemoOnly-2026 token=demo.token.value apiKey=sk_test_abcdefghijklmnop",
     {"PASSWORD", "TOKEN", "API_KEY"}),
    ("identity", "身份证11010519491231002X，卡号4532015112830366。", {"ID_CARD", "BANK_CARD"}),
    ("network", "服务节点10.20.30.40由王磊维护。", {"IP", "PERSON"}),
    ("multiple", "欧阳宁通知陈凯旋和司马安参加会议。", {"PERSON"}),
    ("json", '{"owner":"林浩然","email":"lin@example.com","password":"JsonOnly-2026"}',
     {"PERSON", "EMAIL", "PASSWORD"}),
    ("mixed", "赵敏在云帆数据有限公司处理工单，电话13800138001，token=mixed.demo.token。",
     {"PERSON", "ORG", "PHONE", "TOKEN"}),
]


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--competition-probe", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    recognizer = load_onnx_uie_local(uie_model_dir())
    rows = []
    for name, text, expected in CASES:
        findings = detect(text, extra_candidates=to_findings(text, recognizer.recognize(text)))
        safe, resolved = mask(text, findings)
        recovery = ActiveRecoverySession()
        recovery.replace(resolved)
        restored = recovery.restore(safe).text
        categories = {item.category for item in resolved if item.selected}
        rows.append({"case": name, "original": text,
                     "entities": [{"category": item.category, "text": item.original_value,
                                    "replacement": item.replacement} for item in resolved],
                     "masked": safe, "recovered": restored, "recovery_exact": restored == text,
                     "missing_categories": sorted(expected - categories)})
    payload = {"model_dir": str(uie_model_dir()), "samples": len(rows), "rows": rows,
               "pass": all(row["recovery_exact"] and not row["missing_categories"] for row in rows)}
    args.output.resolve().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
