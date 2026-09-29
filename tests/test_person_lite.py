from safeprompt.core import detect, mask
from safeprompt.ner import to_findings
from safeprompt.person_lite import ChineseNameDetector
from safeprompt.recovery import ActiveRecoverySession


def names(text: str) -> list[str]:
    return [item.text for item in ChineseNameDetector().recognize(text)]


def test_detects_names_with_strong_contexts():
    text = "申请人：张伟；联系人李明；由王强提交；请联系赵晨。"
    assert names(text) == ["张伟", "李明", "王强", "赵晨"]


def test_detects_natural_sentence_and_compound_surnames():
    text = "周明今天反馈问题。陈凯已经确认。顾清扬和迟砚进行了沟通。欧阳明随后提交材料。"
    assert names(text) == ["周明", "陈凯", "顾清扬", "迟砚", "欧阳明"]


def test_handles_extended_dev_contexts_without_absorbing_grammar_characters():
    text = "材料昨天已经交给周明了。陈凯会继续处理。稍后欧阳明再确认一次。"
    assert names(text) == ["周明", "陈凯", "欧阳明"]


def test_hard_negatives_do_not_become_people():
    text = "王者荣耀、陈列数据、李子模块、高性能、高可用、周报、周末、林数据库、何接口、马服务、唐日志、夏系统、金数据、白名单、于今日、任意、沈阳、武汉、杭州、南京。"
    assert names(text) == []


def test_org_like_names_are_not_split_into_people():
    text = "周明数据实验室有限公司、李宁有限公司和王者科技有限公司均已上线。"
    assert names(text) == []


def test_non_overlapping_similar_names_can_coexist_across_connectors():
    text = "周明和周明明，陈凯与陈凯旋，李明、李明明，欧阳明及欧阳明月。"
    assert names(text) == ["周明", "周明明", "陈凯", "陈凯旋", "李明", "李明明", "欧阳明", "欧阳明月"]


def test_similar_names_keep_their_boundary_before_contact_action():
    assert names("周明和周明明联系陈凯。") == ["周明", "周明明", "陈凯"]


def test_long_name_wins_only_when_candidates_overlap_at_the_same_span():
    assert names("周明明反馈问题。陈凯旋确认结果。") == ["周明明", "陈凯旋"]


def test_internal_action_fragment_does_not_become_another_name():
    text = "负责人：夏安。随后夏安再次反馈结果。李安已经提交。王安正在处理。陈安随后确认。赵安继续反馈。"
    assert names(text) == ["夏安", "夏安", "李安", "王安", "陈安", "赵安"]


def test_functional_he_phrases_are_not_people_but_strong_roles_are_allowed():
    functional = "何以处理，何以解决，何时提交，何处部署，何故失败，何为正确，何必重试，何况如此。"
    assert names(functional) == []
    assert names("负责人：何明；联系人：何安；申请人：何以安；何明反馈问题。") == ["何明", "何安", "何以安", "何明"]


def test_extended_functional_he_grammar_keeps_real_names():
    functional = (
        "为何这样处理，为何失败，为何需要重试，为何不能提交，何人负责，何事导致异常，"
        "何种方案更合适，何等重要，何以处理，何以解决，何时提交，何处部署，何故失败，"
        "何为正确，何必重试，何况如此。"
    )
    assert names(functional) == []
    assert names("负责人：何为；联系人：何然；申请人：何为民；何为民反馈问题；负责人：何以安。") == [
        "何为", "何然", "何为民", "何为民", "何以安",
    ]


def test_an_names_keep_recall_without_internal_action_fragments():
    text = (
        "负责人：张安；负责人：陈安；联系人：张安；联系人：陈安。"
        "张安反馈问题，张安再次提交，张安正在处理。"
        "陈安反馈问题，陈安再次提交，陈安正在排查。"
        "刘安反馈问题，刘安再次确认，刘安正在处理。"
        "夏安再次反馈，李安已经提交，王安正在处理。"
    )
    detected = names(text)
    assert detected == [
        "张安", "陈安", "张安", "陈安", "张安", "张安", "张安",
        "陈安", "陈安", "陈安", "刘安", "刘安", "刘安", "夏安", "李安", "王安",
    ]
    assert not {"安再次", "安已经", "安正在"}.intersection(detected)


def test_rc_person_boundary_regression_through_mask_and_recovery():
    text = (
        "负责人：何明\n联系人：何安\n申请人：何以安\n"
        "为何这样处理\n为何失败\n何时提交\n何处部署\n何故失败\n何必重试\n"
        "周明反馈问题\n周明已经提交\n周明明反馈问题\n"
        "陈凯继续处理\n陈凯旋已经提交\n林浩反馈问题\n林浩然已经提交\n"
        "许晨反馈问题\n许晨曦已经提交\n张安再次提交\n陈安正在排查\n刘安已经确认\n"
        "周明科技有限公司\n陈凯信息技术有限公司\n林浩数据中心有限公司\n许晨实验室有限公司\n"
        "原文：<PERSON_1>\n<ORG_1>\n负责人还是周明。"
    )
    results = ChineseNameDetector().recognize(text)
    findings = detect(text, extra_candidates=to_findings(text, results, source="lightweight_person"))
    safe, resolved = mask(text, findings)
    assert "为何这样处理" in safe and "何时提交" in safe
    assert "周明科技有限公司" in safe and "陈凯信息技术有限公司" in safe
    assert "林浩数据中心有限公司" in safe and "许晨实验室有限公司" in safe
    zhou_replacements = {item.replacement for item in resolved if item.original_value == "周明"}
    assert len(zhou_replacements) == 1
    zhou_replacement = zhou_replacements.pop()
    assert safe.count(zhou_replacement) == 3
    assert f"{zhou_replacement}反馈问题" in safe and f"负责人还是{zhou_replacement}" in safe
    assert "<PERSON_1>" in safe and "<ORG_1>" in safe
    assert {item.original_value for item in resolved}.issuperset({"周明", "周明明", "陈凯", "陈凯旋", "林浩", "林浩然", "许晨", "许晨曦"})
    session = ActiveRecoverySession()
    session.replace(resolved)
    assert session.restore(safe).text == text


def test_results_use_existing_finding_expansion_and_mask_pipeline():
    text = "负责人：周明。周明反馈问题，稍后联系周明。"
    results = ChineseNameDetector().recognize(text)
    findings = to_findings(text, results)
    safe, resolved = mask(text, detect(text, extra_candidates=findings))
    assert safe == "负责人：<PERSON_1>。<PERSON_1>反馈问题，稍后联系<PERSON_1>。"
    assert {item.replacement for item in resolved} == {"<PERSON_1>"}
