import json
from pathlib import Path


HARD_CASES = Path(__file__).resolve().parent.parent / "benchmarks" / "ner_hard_cases.jsonl"


def test_recorded_ner_hard_cases_have_valid_observed_offsets():
    rows = [json.loads(line) for line in HARD_CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    case = next(row for row in rows if row["id"] == "org-university-committee")
    assert case["model"] == "uie-nano" and case["position_prob"] == 0.5
    assert case["assessment"] == "partial"
    assert all(case["text"][item["start"]:item["end"]] == item["text"]
               for item in case["observed_results"])
