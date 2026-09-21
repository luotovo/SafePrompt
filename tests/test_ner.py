import time
import math
from threading import Event

from safeprompt.core import detect, mask
from safeprompt.ner import EntityResult, NerService, to_findings


class Recognizer:
    def __init__(self, results=None, error=None, delay=0):
        self.results, self.error, self.delay = results or [], error, delay

    def recognize(self, text):
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.results


def entity(category, start, end, text, confidence=0.99):
    return EntityResult(category, start, end, text, confidence, "test-model")


def test_person_result_becomes_finding_and_masks_consistently():
    text = "韩静联系韩静"
    findings = to_findings(text, [entity("PERSON", 0, 2, "韩静"), entity("PERSON", 4, 6, "韩静")])
    assert all(item.source == "entity_model" for item in findings)
    assert mask(text, detect(text, extra_candidates=findings))[0] == "<PERSON_1>联系<PERSON_1>"


def test_dictionary_wins_equal_ner_overlap():
    text = "中国地质大学"
    ner = to_findings(text, [entity("ORG", 0, len(text), text)])
    finding = detect(text, [(text, "CUSTOMER", True)], extra_candidates=ner)[0]
    assert finding.source == "dictionary" and finding.category == "CUSTOMER"


def test_rule_wins_ner_overlap():
    text = "10.0.0.1"
    ner = to_findings(text, [entity("PERSON", 0, len(text), text)])
    assert detect(text, extra_candidates=ner)[0].category == "IP"


def test_low_confidence_is_filtered():
    thresholds = {"test-model": {"PERSON": 0.8}}
    assert to_findings("韩静", [entity("PERSON", 0, 2, "韩静", 0.2)], thresholds_by_model=thresholds) == []


def test_invalid_entity_results_are_discarded():
    text = "韩静"
    invalid = [
        entity("CUSTOMER", 0, 2, "韩静"), entity("PERSON", -1, 2, "韩静"),
        entity("PERSON", 0, 3, "韩静"), entity("PERSON", 0, 2, "韩错"),
        entity("PERSON", 0, 2, "韩静", math.nan), entity("PERSON", 0, 2, "韩静", math.inf),
        entity("PERSON", 0, 2, "韩静", -0.1), entity("PERSON", 0, 2, "韩静", 1.1),
    ]
    assert to_findings(text, invalid) == []


def test_load_failure_degrades_without_affecting_rules():
    service = NerService(lambda: (_ for _ in ()).throw(OSError("model missing")))
    assert service.recognize("10.0.0.1") == []
    for _ in range(100):
        if service.unavailable:
            break
        time.sleep(0.001)
    assert service.unavailable
    assert detect("10.0.0.1")[0].category == "IP"


def test_inference_failure_degrades_without_affecting_dictionary():
    service = NerService(lambda: Recognizer(error=RuntimeError("bad model")))
    assert service.recognize("客户A") == []
    for _ in range(100):
        if not service.loading:
            break
        time.sleep(0.001)
    assert service.recognize("客户A") == [] and service.unavailable
    assert detect("客户A", [("客户A", "CUSTOMER", True)])[0].category == "CUSTOMER"


def test_timeout_degrades_and_does_not_reload():
    loads = []
    service = NerService(lambda: loads.append(1) or Recognizer(delay=0.05), timeout_seconds=0.001)
    assert service.recognize("文本") == []
    for _ in range(100):
        if not service.loading:
            break
        time.sleep(0.001)
    assert service.recognize("文本") == [] and service.unavailable
    assert service.recognize("文本") == [] and loads == [1]


def test_ner_never_modifies_input_text():
    text = "韩静"
    service = NerService(lambda: Recognizer([entity("PERSON", 0, 2, text)]))
    assert service.recognize(text) == []
    for _ in range(100):
        if not service.loading:
            break
        time.sleep(0.001)
    results = service.recognize(text)
    assert text == "韩静" and results[0].text == text


def test_first_load_is_non_blocking_and_reused():
    release = Event()
    loads = []
    def load():
        release.wait()
        loads.append(1)
        return Recognizer()
    service = NerService(load)
    started = time.perf_counter()
    assert service.recognize("文本") == []
    assert time.perf_counter() - started < 0.1 and service.loading
    assert service.recognize("文本") == [] and loads == []
    release.set()
    for _ in range(100):
        if not service.loading:
            break
        time.sleep(0.001)
    assert service.recognize("文本") == [] and loads == [1]
