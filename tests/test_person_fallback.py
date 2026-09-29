from safeprompt.person_lite import ChineseNameDetector


def names(text: str) -> list[str]:
    return [item.text for item in ChineseNameDetector().recognize(text)]


def test_fallback_completes_high_confidence_three_character_names():
    assert names("顾明远来自北辰云计算有限公司，许清禾来自青禾数据研究院。") == ["顾明远", "许清禾"]


def test_fallback_supports_roles_and_compound_surnames():
    text = "项目负责人沈知远，开发人员陆承安、韩雪，最终审核人为诸葛文博。"
    detected = names(text)
    assert "沈知远" in detected and "陆承安" in detected and "诸葛文博" in detected


def test_fallback_rejects_functional_and_technical_terms():
    text = "何时何以何处何故何为何必何况。高性能模式开启，周末检查日志、系统、接口、项目和数据库。"
    assert names(text) == []
