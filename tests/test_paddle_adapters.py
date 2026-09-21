from safeprompt.adapters.paddle import TaskflowNerRecognizer, UieNanoRecognizer, deny_network
from safeprompt.ner import to_findings


def test_uie_maps_only_person_and_org_with_real_probability():
    predictor = lambda text: [{"人名": [{"text": "韩静", "start": 0, "end": 2, "probability": 0.92}],
                               "组织机构": [{"text": "海川大学", "start": 3, "end": 7, "probability": 0.88}],
                               "项目": [{"text": "升级项目", "start": 8, "end": 12, "probability": 0.99}]}]
    results = UieNanoRecognizer(predictor).recognize("韩静在海川大学的升级项目")
    assert [(item.category, item.confidence) for item in results] == [("PERSON", 0.92), ("ORG", 0.88)]


def test_taskflow_maps_per_org_without_fabricating_confidence():
    predictor = lambda text: [[("韩静", "PER"), ("在", "p"), ("海川大学", "ORG")]]
    text = "韩静在海川大学"
    results = TaskflowNerRecognizer(predictor).recognize(text)
    assert [item.confidence for item in results] == [None, None]
    assert [(item.start, item.end) for item in results] == [(0, 2), (3, 7)]
    assert to_findings(text, results) == []


def test_local_model_load_guard_blocks_network():
    import socket
    try:
        with deny_network():
            socket.create_connection(("example.com", 443))
    except RuntimeError as error:
        assert "network access blocked" in str(error)
    else:
        raise AssertionError("network guard allowed a connection")


def test_uie_missing_local_model_fails_before_import(tmp_path):
    try:
        UieNanoRecognizer.from_local_path(tmp_path)
    except FileNotFoundError as error:
        assert "incomplete local UIE model" in str(error)
    else:
        raise AssertionError("missing model was accepted")
