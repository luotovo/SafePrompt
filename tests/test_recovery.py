from safeprompt.core import detect, mask
from safeprompt.recovery import ActiveRecoverySession


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def session_for(text="韩静访问10.0.0.1", ttl=900):
    clock = Clock()
    safe, findings = mask(text, detect(text, [("韩静", "PERSON")]))
    session = ActiveRecoverySession(ttl, clock)
    session.replace(findings)
    return session, clock, safe


def test_default_window_is_fifteen_minutes():
    assert ActiveRecoverySession().ttl_seconds == 900


def test_known_placeholders_restore_every_occurrence():
    session, _, _ = session_for()
    result = session.restore("<PERSON_1>回复<PERSON_1>，地址<IP_1>")
    assert result.text == "韩静回复韩静，地址10.0.0.1"
    assert (result.restored_count, result.unknown_count) == (3, 0)


def test_unknown_legal_placeholder_is_preserved_and_counted():
    session, _, _ = session_for()
    result = session.restore("保留<PERSON_99>和<ORG_1>")
    assert result.text == "保留<PERSON_99>和<ORG_1>" and result.unknown_count == 2


def test_unknown_category_is_not_treated_as_legal_placeholder():
    session, _, _ = session_for()
    result = session.restore("<MADE_UP_1>")
    assert result.text == "<MADE_UP_1>" and result.unknown_count == 0


def test_malformed_placeholders_are_not_guessed_or_counted():
    session, _, _ = session_for()
    text = "<PERSON_0> <PERSON_-1> <person_1> <PERSON_01> PERSON_1"
    result = session.restore(text)
    assert result.text == text and result.unknown_count == 0


def test_new_mapping_overwrites_old_mapping():
    session, _, _ = session_for()
    _, newer = mask("李珊", detect("李珊", [("李珊", "PERSON")]))
    session.replace(newer)
    assert session.restore("<PERSON_1>").text == "李珊"


def test_expiry_releases_mapping():
    session, clock, _ = session_for(ttl=10)
    clock.now = 10
    assert not session.active
    assert session.restore("<PERSON_1>").unknown_count == 1


def test_manual_clear_releases_mapping():
    session, _, _ = session_for()
    session.clear()
    assert not session.active


def test_empty_replacement_clears_previous_mapping():
    session, _, _ = session_for()
    session.replace([])
    assert not session.active


def test_unselected_finding_is_not_saved():
    session, _, _ = session_for()
    _, findings = mask("韩静", detect("韩静", [("韩静", "PERSON", False)]))
    session.replace(findings)
    assert not session.active


def test_text_without_placeholders_is_unchanged():
    session, _, _ = session_for()
    result = session.restore("普通 AI 回复")
    assert result.text == "普通 AI 回复" and result.restored_count == result.unknown_count == 0


def test_placeholder_matching_is_exact_and_case_sensitive():
    session, _, _ = session_for()
    result = session.restore("x<PERSON_1>y <Person_1>")
    assert result.text == "x韩静y <Person_1>" and result.restored_count == 1


def test_original_mask_mapping_ai_restore_end_to_end():
    original = "韩静从10.0.0.1提交，韩静复核。"
    safe, findings = mask(original, detect(original, [("韩静", "PERSON")]))
    session = ActiveRecoverySession()
    session.replace(findings)
    ai_reply = f"收到：{safe} 未知<ORG_8>"
    result = session.restore(ai_reply)
    assert result.text == f"收到：{original} 未知<ORG_8>"
    assert (result.restored_count, result.unknown_count) == (3, 1)
