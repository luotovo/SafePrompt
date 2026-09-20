from benchmarks.ner_dataset import samples
from benchmarks.run_ner_benchmark import rss_bytes, score
from safeprompt.ner import EntityResult
import time


class AccuracyThenEmptyRecognizer:
    def __init__(self):
        self.calls = {}
        self.gold = {row["text"]: row["entities"] for row in samples()}

    def recognize(self, text):
        self.calls[text] = self.calls.get(text, 0) + 1
        if self.calls[text] != 1:
            return []
        return [EntityResult(item["category"], item["start"], item["end"], item["text"], 0.5, "fake")
                for item in self.gold[text]]


def test_accuracy_prediction_is_separate_from_timing_runs():
    result = score(AccuracyThenEmptyRecognizer(), repeats=2)
    assert result["metrics"]["PERSON"]["f1"] == 1
    assert result["metrics"]["ORG"]["f1"] == 1
    assert result["p95_latency_ms"] >= 0 and result["max_latency_ms"] >= result["p95_latency_ms"]


def test_windows_rss_is_readable():
    assert rss_bytes() > 0


def test_normal_and_long_text_latency_are_separate():
    class LengthTimedRecognizer:
        def recognize(self, text):
            time.sleep(0.01 if len(text) >= 1000 else 0.001)
            return []

    result = score(LengthTimedRecognizer(), repeats=1)
    assert result["max_latency_ms"] < result["long_text_latency_ms"]
