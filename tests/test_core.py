import pytest

from safeprompt.core import Finding, detect, mask
from safeprompt.recovery import ActiveRecoverySession


def test_consistent_masking() -> None:
    text = "韩静访问10.21.3.15，电话13812345678；password=123456；再访问10.21.3.15"
    safe, _ = mask(text, detect(text, [("韩静", "PERSON")]))
    assert safe == "<PERSON_1>访问<IP_1>，电话<PHONE_1>；password=<PASSWORD_1>；再访问<IP_1>"


def test_mask_skips_placeholders_already_present_in_original_text() -> None:
    text = "周明说 <PERSON_1> 是业务模板。"
    safe, findings = mask(text, detect(text, [("周明", "PERSON", True)]))
    assert safe == "<PERSON_2>说 <PERSON_1> 是业务模板。"
    recovery = ActiveRecoverySession()
    recovery.replace(findings)
    assert recovery.restore(safe).text == text


def test_mask_skips_multiple_reserved_placeholders_deterministically() -> None:
    text = "<PERSON_1> 周明 <PERSON_2> 陈浩 <PERSON_5> 周明"
    safe, _ = mask(text, detect(text, [("周明", "PERSON", True), ("陈浩", "PERSON", True)]))
    assert safe == "<PERSON_1> <PERSON_3> <PERSON_2> <PERSON_4> <PERSON_5> <PERSON_3>"


def test_reserved_placeholders_are_independent_per_category() -> None:
    text = "<ID_1> 123456 <EMAIL_1> a@example.com <ORG_1> 星河科技"
    safe, _ = mask(text, detect(text, [
        ("123456", "ID", True), ("星河科技", "ORG", True),
    ]))
    assert safe == "<ID_1> <ID_2> <EMAIL_1> <EMAIL_2> <ORG_1> <ORG_2>"


def test_unknown_original_placeholder_is_never_added_to_recovery_mapping() -> None:
    text = "周明说 <PERSON_99> 是上游模板。"
    safe, findings = mask(text, detect(text, [("周明", "PERSON", True)]))
    recovery = ActiveRecoverySession()
    recovery.replace(findings)
    assert safe == "<PERSON_1>说 <PERSON_99> 是上游模板。"
    assert recovery.restore(safe).text == text


def test_only_complete_uppercase_placeholders_are_reserved() -> None:
    text = "周明 person2 2person <person_3> PERSON_4"
    assert mask(text, detect(text, [("周明", "PERSON", True)]))[0].startswith("<PERSON_1>")


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


@pytest.mark.parametrize("text", ["邮箱name@example.com", "李娜邮箱lina@example.com。"])
def test_email_after_chinese_context_is_fully_masked(text: str) -> None:
    findings = detect(text)
    assert [(item.category, item.original_value) for item in findings] == [
        ("EMAIL", text[text.index("name@"):] if "name@" in text else "lina@example.com"),
    ]
    assert "@<DOMAIN_" not in mask(text, findings)[0]


def test_bank_card_requires_valid_luhn_checksum() -> None:
    text = "有效卡号4532015112830366，无效卡号4532015112830367"
    findings = detect(text)
    assert [(item.category, item.original_value) for item in findings] == [
        ("BANK_CARD", "4532015112830366"),
    ]
    assert mask(text, findings)[0] == "有效卡号<BANK_CARD_1>，无效卡号4532015112830367"


def test_competition_valid_card_and_non_luhn_card_policy() -> None:
    text = "有效卡4111111111111111，无效卡6222021234567890123"
    assert [(item.category, item.original_value) for item in detect(text)] == [
        ("BANK_CARD", "4111111111111111")]


@pytest.mark.parametrize("text,value", [
    ("数据库密码：Demo_DB_2026!", "Demo_DB_2026!"),
    ("数据库密码为 Demo_DB_2026!", "Demo_DB_2026!"),
    ("登录密码：Demo_Login_2026!", "Demo_Login_2026!"),
    ("管理员口令：Demo_Admin_2026!", "Demo_Admin_2026!"),
    ("DB_PASSWORD=Demo_DB_2026!", "Demo_DB_2026!"),
])
def test_high_confidence_chinese_password_labels(text, value) -> None:
    assert [(item.category, item.original_value) for item in detect(text)] == [("PASSWORD", value)]


@pytest.mark.parametrize("text", ["密码文档", "数据库密码策略", "管理员口令要求"])
def test_chinese_password_labels_require_value_delimiter(text) -> None:
    assert detect(text) == []


@pytest.mark.parametrize("text,value", [
    ("API_KEY=sk-test-f92a81bc73de456789012345", "sk-test-f92a81bc73de456789012345"),
    ("api-key: sk-test-a71c93de82bf456789012345", "sk-test-a71c93de82bf456789012345"),
    ('"apiKey": "sk-test-c83d20fa91be456789012345"', "sk-test-c83d20fa91be456789012345"),
    ("API Key 为 sk-test-b67132f95a204ec883190002", "sk-test-b67132f95a204ec883190002"),
])
def test_api_key_high_confidence_labels(text, value) -> None:
    assert [(item.category, item.original_value) for item in detect(text)] == [("API_KEY", value)]


@pytest.mark.parametrize("text", ["API_KEY_ENABLED=true", "api_key_name=test-key", "API Key 文档"])
def test_api_key_label_hard_negatives(text) -> None:
    assert detect(text) == []


@pytest.mark.parametrize("text,value", [
    ("Token：`demo-token-a8163cf9d0214e62`", "demo-token-a8163cf9d0214e62"),
    ("Access Token：demo-token-a8163cf9d0214e62", "demo-token-a8163cf9d0214e62"),
    ("访问令牌：demo-token-a8163cf9d0214e62", "demo-token-a8163cf9d0214e62"),
])
def test_token_labels_support_chinese_punctuation_and_markdown(text, value) -> None:
    assert [(item.category, item.original_value) for item in detect(text)] == [("TOKEN", value)]


def test_ipv6_is_supported_with_standard_parser_validation() -> None:
    text = "IPv6：2001:db8:85a3::8a2e:370:7334"
    assert [(item.category, item.original_value) for item in detect(text)] == [
        ("IP", "2001:db8:85a3::8a2e:370:7334")]


@pytest.mark.parametrize("text", [
    "u.name", "u.phone", "u.email", "user.name", "user.phone", "user.email",
    "config.timeout", "result.code", "report.docx", "v2.3.1", "3.12.4",
])
def test_domain_hard_negatives(text) -> None:
    assert not any(item.category == "DOMAIN" for item in detect(text))


@pytest.mark.parametrize("domain", [
    "api.safe-demo.example.com", "admin.safe-demo.example.com", "backup.safe-demo.example.com",
])
def test_domain_true_positives(domain) -> None:
    assert [(item.category, item.original_value) for item in detect(domain)] == [("DOMAIN", domain)]


def test_id_card_after_chinese_context_is_fully_masked() -> None:
    text = "身份证11010519491231002X，已核验"
    findings = detect(text)
    assert [(item.category, item.original_value) for item in findings] == [
        ("ID_CARD", "11010519491231002X"),
    ]
    assert mask(text, findings)[0] == "身份证<ID_CARD_1>，已核验"


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


@pytest.mark.parametrize("key", [
    "id", "Id", "ID", "fdId", "fdDocId", "fdModelId", "recordId", "userId", "creatorId", "xxx_id",
    "UserID", "USERID", "User_ID", "USER_ID", "RecordID", "RECORD_ID",
])
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


@pytest.mark.parametrize("key", ["UserID", "USERID", "User_ID", "USER_ID", "RecordID", "RECORD_ID"])
def test_case_insensitive_identifier_assignments_preserve_keys(key: str) -> None:
    assert mask(f"{key}=55667788", detect(f"{key}=55667788"))[0] == f"{key}=<ID_1>"


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
