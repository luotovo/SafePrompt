from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from safeprompt.adapters.onnx_uie import load_onnx_uie_local
from safeprompt.core import detect, mask
from safeprompt.ner import to_findings
from safeprompt.person_lite import ChineseNameDetector
from safeprompt.recovery import ActiveRecoverySession


CORPUS_PATH = Path(__file__).parent / "data" / "competition_manual_regression.json"


def load_corpus() -> list[dict]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def assert_case(case: dict, findings: list) -> None:
    actual = {}
    for finding in findings:
        actual.setdefault(finding.category, set()).add(finding.original_value)
    for category, expected_values in case.get("expected", {}).items():
        if category == "ORG":
            assert all(any(expected in value or value in expected for value in actual.get(category, set()))
                       for expected in expected_values), case["id"]
        else:
            assert set(expected_values) <= actual.get(category, set()), case["id"]
    if case.get("require_org"):
        assert actual.get("ORG"), case["id"]
    for category in case.get("forbidden", []):
        assert not actual.get(category), case["id"]
    assert not set(case.get("forbidden_person_values", [])) & actual.get("PERSON", set()), case["id"]


def test_manual_regression_fixture_is_substantial_and_unique() -> None:
    corpus = load_corpus()
    assert len(corpus) >= 50
    assert len({case["id"] for case in corpus}) == len(corpus)


def test_manual_structured_regressions_without_model() -> None:
    for case in load_corpus():
        if (case.get("require_org")
                or any(category in case.get("expected", {}) for category in ("PERSON", "ORG"))):
            continue
        assert_case(case, detect(case["text"]))


@pytest.mark.skipif(not os.environ.get("SAFEPROMPT_UIE_ONNX_DIR"),
                    reason="competition model path is supplied only at the Hybrid release gate")
def test_complete_manual_regression_with_hybrid_model() -> None:
    recognizer = load_onnx_uie_local(Path(os.environ["SAFEPROMPT_UIE_ONNX_DIR"]))
    fallback = ChineseNameDetector()
    for case in load_corpus():
        text = case["text"]
        candidates = to_findings(text, recognizer.recognize(text))
        candidates.extend(to_findings(text, fallback.recognize(text), source="lightweight_person"))
        findings = detect(text, extra_candidates=candidates)
        assert_case(case, findings)
        safe, resolved = mask(text, findings)
        recovery = ActiveRecoverySession()
        recovery.replace(resolved)
        assert recovery.restore(safe).text == text, case["id"]
