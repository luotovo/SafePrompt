import pytest

from safeprompt.core import Finding, detect, mask
from safeprompt.recovery import ActiveRecoverySession


def test_consistent_masking() -> None:
    text = "韩静访问10.21.3.15，电话13812345678；password=123456；再访问10.21.3.15"
    safe, _ = mask(text, detect(text, [("韩静", "PERSON")]))
    assert safe == "<PERSON_1>访问<IP_1>，电话<PHONE_1>；password=<PASSWORD_1>；再访问<IP_1>"


def test_db_credential_overrides_ip() -> None:
    findings = detect("jdbc:mysql://10.21.3.15:3306/test?user=admin&password=123456")
    assert [item.category for item in findings] == ["DB_CREDENTIAL"]


def test_bearer_token() -> None:
    text = "Authorization: Bearer eyJabc.DEF_123.GHI-456"
    safe, resolved = mask(text, detect(text))
    assert safe == "Authorization: Bearer <TOKEN_1>"
    recovery = ActiveRecoverySession()
    recovery.replace(resolved)
    assert recovery.restore(safe).text == text


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
def test_bearer_token_preserves_authentication_scheme(scheme: str) -> None:
    text = f"Authorization: {scheme} abc123.signature"
    findings = detect(text)
    assert [(item.category, item.original_value) for item in findings] == [("TOKEN", "abc123.signature")]
    assert mask(text, findings)[0] == f"Authorization: {scheme} <TOKEN_1>"


def test_token_assignment_and_api_key_behavior_remain_supported() -> None:
    text = "token=abc123.signature apiKey=sk_abcdefghijklmnop"
    assert mask(text, detect(text))[0] == "token=<TOKEN_1> apiKey=<API_KEY_1>"


def test_json_password_and_chinese_punctuation() -> None:
    text = '{"password":"123456"}，访问 https://example.com/api，随后报错'
    findings = detect(text)
    assert [(item.category, item.original_value) for item in findings] == [
        ("PASSWORD", "123456"), ("URL", "https://example.com/api"),
    ]
    assert mask(text, findings)[0] == '{"password":"<PASSWORD_1>"}，访问 <URL_1>，随后报错'


def test_env_password_preserves_field_name() -> None:
    text = "password=123456"
    assert mask(text, detect(text))[0] == "password=<PASSWORD_1>"


def test_jdbc_stops_at_chinese_punctuation() -> None:
    finding = detect("jdbc:mysql://10.0.0.1/test，连接失败")[0]
    assert finding.original_value == "jdbc:mysql://10.0.0.1/test"


def test_dictionary_uses_longest_match_and_ascii_word_boundary() -> None:
    findings = detect("username user Portal Upgrade", [("user", "FIELD_NAME"), ("Portal", "SYSTEM"), ("Portal Upgrade", "PROJECT")])
    assert [(item.category, item.original_value) for item in findings] == [("FIELD_NAME", "user"), ("PROJECT", "Portal Upgrade")]


def test_category_defaults_apply_to_rules_and_preserve_core_defaults() -> None:
    findings = detect("10.0.0.1 password=abc", category_defaults={"IP": False, "PASSWORD": False})
    assert [(item.category, item.selected) for item in findings] == [("IP", False), ("PASSWORD", False)]
    assert detect("a@example.com")[0].selected is True


def test_dictionary_default_overrides_category_default() -> None:
    finding = detect("客户A", [("客户A", "CUSTOMER", True)], {"CUSTOMER": False})[0]
    assert finding.selected is True


def test_source_priority_is_explicit_within_same_category_layer() -> None:
    text = "韩静"
    model = Finding("PERSON", 0, 2, text, "entity_model", "medium")
    assert detect(text, [(text, "PERSON", True)], extra_candidates=[model])[0].source == "dictionary"


@pytest.mark.parametrize("key", ["id", "Id", "ID", "fdId", "fdDocId", "fdModelId", "recordId", "userId", "creatorId", "xxx_id"])
def test_structured_identifier_keys_mask_only_their_values(key: str) -> None:
    text = f'"{key}": "123456"'
    findings = detect(text)
    assert [(item.category, item.original_value, item.risk_level) for item in findings] == [
        ("ID", "123456", "medium")
    ]
    assert mask(text, findings)[0] == f'"{key}": "<ID_1>"'


def test_assignment_identifier_preserves_key_and_leading_zeroes() -> None:
    text = "creatorId=068226 record_id=abc-123"
    assert mask(text, detect(text))[0] == "creatorId=<ID_1> record_id=<ID_2>"


def test_identifier_category_default_can_disable_masking() -> None:
    finding = detect('"fdId":"123456"', category_defaults={"ID": False})[0]
    assert finding.category == "ID" and finding.risk_level == "medium" and finding.selected is False


def test_repeated_identifier_value_reuses_placeholder() -> None:
    text = '{"fdId":"2309820071649066686","fdDocId":"2309820071649066686"}'
    assert mask(text, detect(text))[0] == '{"fdId":"<ID_1>","fdDocId":"<ID_1>"}'


@pytest.mark.parametrize("text", [
    "totalSize=57", "status=30", "timestamp=1669861639000", "page=1", "count=100",
    '"ROW_ID": 1', "VALID=123",
])
def test_plain_numbers_without_strong_identifier_context_are_not_ids(text: str) -> None:
    assert all(item.category != "ID" for item in detect(text))


def test_large_json_masks_contextual_ids_without_numeric_false_positives() -> None:
    text = '''{
  "totalSize": 57,
  "content": [
    {
      "fdId": "2309820071649066686",
      "fdCreator": {"fdId": "068226"},
      "fdCreateTime": 1669861639000,
      "fdProcessStatus": "30",
      "fdDocId": "2309820071649066686",
      "fdModelId": "2309820071649066686"
    }
  ]
}'''
    safe, findings = mask(text, detect(text))
    assert [(item.category, item.original_value) for item in findings] == [
        ("ID", "2309820071649066686"), ("ID", "068226"),
        ("ID", "2309820071649066686"), ("ID", "2309820071649066686"),
    ]
    assert '"totalSize": 57' in safe and '"fdCreateTime": 1669861639000' in safe
    assert safe.count('"<ID_1>"') == 3 and '"fdId": "<ID_2>"' in safe
