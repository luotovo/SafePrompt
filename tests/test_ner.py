import time
import math
from threading import Event

from safeprompt.core import detect, mask
from safeprompt.recovery import ActiveRecoverySession
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


def test_model_person_seed_expands_to_every_safe_exact_occurrence():
    text = "周明反馈问题，负责人是周明，稍后联系周明。"
    findings = to_findings(text, [entity("PERSON", 0, 2, "周明")])
    safe, resolved = mask(text, detect(text, extra_candidates=findings))
    assert [(item.start, item.end) for item in resolved] == [(0, 2), (11, 13), (18, 20)]
    assert safe == "<PERSON_1>反馈问题，负责人是<PERSON_1>，稍后联系<PERSON_1>。"


def test_person_expansion_keeps_multiple_entities_consistent():
    text = "周明联系陈浩，稍后周明再次联系陈浩。"
    findings = to_findings(text, [
        entity("PERSON", 0, 2, "周明"), entity("PERSON", 4, 6, "陈浩"),
        entity("PERSON", 11, 13, "陈浩"),
    ])
    assert mask(text, detect(text, extra_candidates=findings))[0] == (
        "<PERSON_1>联系<PERSON_2>，稍后<PERSON_1>再次联系<PERSON_2>。")


def test_org_seed_expands_to_every_safe_exact_occurrence():
    text = "星河科技有限公司提交材料，星河科技有限公司随后确认。"
    findings = to_findings(text, [entity("ORG", 0, 8, "星河科技有限公司")])
    assert mask(text, detect(text, extra_candidates=findings))[0] == (
        "<ORG_1>提交材料，<ORG_1>随后确认。")


def test_model_occurrence_expansion_does_not_duplicate_existing_spans():
    text = "周明联系周明。"
    findings = to_findings(text, [
        entity("PERSON", 0, 2, "周明"), entity("PERSON", 4, 6, "周明"),
    ])
    assert [(item.start, item.end) for item in findings] == [(0, 2), (4, 6)]


def test_occurrence_expansion_avoids_obvious_person_and_org_substrings():
    people = "周明明和周明"
    person_findings = to_findings(people, [entity("PERSON", 4, 6, "周明")])
    assert [(item.start, item.end) for item in person_findings] == [(4, 6)]
    orgs = "中国共产党中国地质大学（武汉）委员会与中国地质大学合作"
    start = orgs.rindex("中国地质大学")
    org_findings = to_findings(orgs, [entity("ORG", start, start + 6, "中国地质大学")])
    assert [(item.start, item.end) for item in org_findings] == [(start, start + 6)]


def test_expanded_person_findings_share_one_recovery_mapping():
    text = "周明反馈问题，负责人是周明，稍后联系周明。"
    safe, resolved = mask(text, detect(text, extra_candidates=to_findings(
        text, [entity("PERSON", 0, 2, "周明")])) )
    session = ActiveRecoverySession()
    session.replace(resolved)
    restored = session.restore(safe)
    assert restored.text == text and restored.restored_count == 3


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
