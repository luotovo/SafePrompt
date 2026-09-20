from safeprompt.core import Finding, detect, mask


def test_consistent_masking() -> None:
    text = "韩静访问10.21.3.15，电话13812345678；password=123456；再访问10.21.3.15"
    safe, _ = mask(text, detect(text, [("韩静", "PERSON")]))
    assert safe == "<PERSON_1>访问<IP_1>，电话<PHONE_1>；password=<PASSWORD_1>；再访问<IP_1>"


def test_db_credential_overrides_ip() -> None:
    findings = detect("jdbc:mysql://10.21.3.15:3306/test?user=admin&password=123456")
    assert [item.category for item in findings] == ["DB_CREDENTIAL"]


def test_bearer_token() -> None:
    text = "Authorization: Bearer eyJabc.DEF_123.GHI-456"
    assert "<TOKEN_1>" in mask(text, detect(text))[0]


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
