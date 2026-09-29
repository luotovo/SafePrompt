import socket
import time

from safeprompt.core import Finding, detect, mask
from safeprompt.ner import EntityResult, NerService, to_findings
from safeprompt.person_lite import ChineseNameDetector
from safeprompt.recovery import ActiveRecoverySession


def _entity(category: str, start: int, end: int, text: str) -> EntityResult:
    return EntityResult(category, start, end, text, 0.99, "uie-nano")


def _lite_findings(text: str, defaults=None):
    return to_findings(text, ChineseNameDetector().recognize(text), defaults, source="lightweight_person")


def test_missing_uie_still_masks_people_with_lightweight_detector():
    service = NerService(lambda: (_ for _ in ()).throw(FileNotFoundError("model missing")))
    text = "负责人：周明\n联系人：陈凯\n周明稍后联系陈凯。"
    findings = detect(text, extra_candidates=[*_lite_findings(text), *to_findings(text, service.recognize(text))])
    safe, _ = mask(text, findings)
    assert safe == "负责人：<PERSON_1>\n联系人：<PERSON_2>\n<PERSON_1>稍后联系<PERSON_2>。"
    for _ in range(100):
        if service.unavailable:
            break
        time.sleep(0.001)
    assert service.unavailable


def test_uie_and_lightweight_person_share_one_finding_and_placeholder():
    text = "周明反馈远航数据科技有限公司异常。"
    organization = "远航数据科技有限公司"
    uie = to_findings(text, [_entity("PERSON", 0, 2, "周明"),
                            _entity("ORG", 4, 4 + len(organization), organization)])
    findings = detect(text, extra_candidates=[*uie, *_lite_findings(text)])
    safe, resolved = mask(text, findings)
    assert [(item.category, item.source) for item in resolved] == [("PERSON", "entity_model"), ("ORG", "entity_model")]
    assert safe == "<PERSON_1>反馈<ORG_1>异常。"


def test_lightweight_person_wins_over_overlapping_dictionary_and_uie_org():
    text = "李宁有限公司"
    lite = [Finding("PERSON", 0, 2, "李宁", "lightweight_person", "medium")]
    dictionary = detect(text, [(text, "ORG", True)], extra_candidates=lite)
    uie = detect(text, extra_candidates=[*lite, *to_findings(text, [_entity("ORG", 0, len(text), text)])])
    assert [(item.category, item.source) for item in dictionary] == [("PERSON", "lightweight_person")]
    assert [(item.category, item.source) for item in uie] == [("PERSON", "lightweight_person")]


def test_lightweight_source_obeys_person_default_and_reuses_existing_expansion():
    text = "负责人：周明。周明反馈问题，稍后联系周明。"
    findings = detect(text, category_defaults={"PERSON": False},
                      extra_candidates=_lite_findings(text, {"PERSON": False}))
    assert {item.source for item in findings} == {"lightweight_person"}
    assert len(findings) == 3 and not any(item.selected for item in findings)


def test_lightweight_person_keeps_reserved_placeholder_and_recovers_all_occurrences():
    text = "周明说 <PERSON_1> 是业务模板。随后周明确认。"
    safe, resolved = mask(text, detect(text, extra_candidates=_lite_findings(text)))
    assert safe == "<PERSON_2>说 <PERSON_1> 是业务模板。随后<PERSON_2>确认。"
    session = ActiveRecoverySession()
    session.replace(resolved)
    assert session.restore(safe).text == text


def test_lightweight_detector_is_offline_and_keeps_similar_names_intact(monkeypatch):
    attempts = []
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: attempts.append(args) or None)
    text = "周明和周明明，陈凯和陈凯旋。"
    assert [item.text for item in ChineseNameDetector().recognize(text)] == ["周明", "周明明", "陈凯", "陈凯旋"]
    assert attempts == []
