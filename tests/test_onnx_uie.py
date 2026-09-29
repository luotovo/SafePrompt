from __future__ import annotations

import socket
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from safeprompt.adapters.onnx_uie import OnnxUieNanoRecognizer, deny_network, split_text
from safeprompt.app import entity_model_enabled
from safeprompt.core import detect, mask
from safeprompt.ner import NerService, to_findings
from safeprompt.recovery import ActiveRecoverySession


class StubTokenizer:
    def encode_pair(self, prompt, text):
        offsets = [[0, 0], [0, len(prompt)], [0, 0]]
        offsets.extend([index, index + 1] for index in range(len(text)))
        offsets.append([0, 0])
        padding = 512 - len(offsets)
        return {
            "input_ids": [1] * len(offsets) + [0] * padding,
            "token_type_ids": [0, 0, 0] + [1] * (len(text) + 1) + [0] * padding,
            "position_ids": list(range(len(offsets))) + [0] * padding,
            "attention_mask": [1] * len(offsets) + [0] * padding,
            "offset_mapping": offsets + [[0, 0]] * padding,
        }


class StubSession:
    def __init__(self, spans=None, error=None):
        self.spans = spans or {"人名": (0, 2), "组织机构": (3, 11)}
        self.error = error
        self.calls = 0

    def get_inputs(self):
        return [SimpleNamespace(name=name) for name in
                ("input_ids", "token_type_ids", "position_ids", "attention_mask")]

    def run(self, outputs, inputs):
        self.calls += 1
        if self.error:
            raise self.error
        start = np.zeros((1, 512), dtype=np.float32)
        end = np.zeros((1, 512), dtype=np.float32)
        span = list(self.spans.values())[(self.calls - 1) % 2]
        start[0, span[0] + 3] = 0.9
        end[0, span[1] - 1 + 3] = 0.9
        return start, end


def test_backend_returns_person_and_org_candidates_for_existing_pipeline():
    text = "周明在星河科技有限公司"
    recognizer = OnnxUieNanoRecognizer(StubSession(), StubTokenizer())
    results = recognizer.recognize(text)
    assert [(item.category, item.start, item.end, item.text) for item in results] == [
        ("PERSON", 0, 2, "周明"), ("ORG", 3, 11, "星河科技有限公司")]
    findings = detect(text, extra_candidates=to_findings(text, results))
    assert mask(text, findings)[0] == "<PERSON_1>在<ORG_1>"


def test_long_text_chunks_overlap_without_gaps():
    chunks = split_text("abcdefghijklmnopqrstuvwxyz", "人名", max_length=12, overlap=3)
    assert chunks == [
        {"text": "abcdefg", "start": 0, "end": 7},
        {"text": "efghijk", "start": 4, "end": 11},
        {"text": "ijklmno", "start": 8, "end": 15},
        {"text": "mnopqrs", "start": 12, "end": 19},
        {"text": "qrstuvw", "start": 16, "end": 23},
        {"text": "uvwxyz", "start": 20, "end": 26},
    ]


@pytest.mark.parametrize("defaults, expected", [
    ({"PERSON": True, "ORG": False}, True),
    ({"PERSON": False, "ORG": True}, True),
    ({"PERSON": False, "ORG": False}, False),
])
def test_category_control_prevents_load_when_both_entity_categories_disabled(defaults, expected):
    assert entity_model_enabled(defaults) is expected


def test_disabled_category_is_not_masked():
    text = "周明在星河科技有限公司"
    results = OnnxUieNanoRecognizer(StubSession(), StubTokenizer()).recognize(text)
    person_off = detect(text, category_defaults={"PERSON": False, "ORG": True},
                        extra_candidates=to_findings(text, results, {"PERSON": False, "ORG": True}))
    org_off = detect(text, category_defaults={"PERSON": True, "ORG": False},
                     extra_candidates=to_findings(text, results, {"PERSON": True, "ORG": False}))
    assert mask(text, person_off)[0] == "周明在<ORG_1>"
    assert mask(text, org_off)[0] == "<PERSON_1>在星河科技有限公司"


@pytest.mark.parametrize("missing", ["model.onnx", "vocab.txt", "tokenizer_config.json", "config.json"])
def test_missing_local_asset_is_explicit(missing, tmp_path):
    for name in ("model.onnx", "vocab.txt", "tokenizer_config.json", "config.json"):
        if name != missing:
            (tmp_path / name).write_bytes(b"x")
    with pytest.raises(FileNotFoundError, match=missing):
        OnnxUieNanoRecognizer.from_local_path(tmp_path)


def test_session_creation_failure_is_explicit(monkeypatch, tmp_path):
    for name in ("model.onnx", "vocab.txt", "tokenizer_config.json", "config.json"):
        (tmp_path / name).write_bytes(b"x")
    fake = SimpleNamespace(InferenceSession=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad session")))
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    with pytest.raises(RuntimeError, match="bad session"):
        OnnxUieNanoRecognizer.from_local_path(tmp_path)


def test_inference_failure_degrades_without_breaking_rule_or_dictionary():
    service = NerService(lambda: OnnxUieNanoRecognizer(StubSession(error=RuntimeError("bad inference")),
                                                       StubTokenizer()))
    service.start_loading()
    while service.loading:
        pass
    assert service.recognize("客户A 10.0.0.1") == []
    assert service.unavailable
    findings = detect("客户A 10.0.0.1", [("客户A", "CUSTOMER", True)])
    assert {item.category for item in findings} == {"CUSTOMER", "IP"}


def test_same_entity_placeholder_collision_and_recovery():
    text = "<PERSON_1> 周明反馈。周明已提交。周明科技有限公司负责实施。"
    results = [
        SimpleNamespace(category="PERSON", start=11, end=13, text="周明", confidence=0.9,
                        model="uie-nano-onnx"),
        SimpleNamespace(category="ORG", start=22, end=30, text="周明科技有限公司", confidence=0.9,
                        model="uie-nano-onnx"),
    ]
    findings = detect(text, extra_candidates=to_findings(text, results))
    safe, resolved = mask(text, findings)
    assert safe == "<PERSON_1> <PERSON_2>反馈。<PERSON_2>已提交。<ORG_1>负责实施。"
    recovery = ActiveRecoverySession()
    recovery.replace(resolved)
    assert recovery.restore(safe).text == text


def test_backend_network_guard_blocks_connections():
    with deny_network(), pytest.raises(RuntimeError, match="network access blocked"):
        socket.create_connection(("example.com", 443))
