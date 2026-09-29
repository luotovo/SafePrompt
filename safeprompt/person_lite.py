"""Deterministic, offline Chinese PERSON detector used only by the V1.1 spike."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .ner import EntityResult


# This is intentionally a practical common-surname set, not a claim of complete
# coverage of Chinese surnames.
SURNAMES = frozenset(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何林高罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦傅方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严赖覃洪武莫孔汤向常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧迟"
)
COMPOUND_SURNAMES = tuple(sorted((
    "欧阳", "司马", "上官", "诸葛", "夏侯", "东方", "皇甫", "尉迟", "公孙", "慕容", "司徒", "司空",
), key=len, reverse=True))

STOPWORDS = frozenset({
    "王者荣耀", "王者", "李子", "李子模块", "陈列", "陈列数据", "高性能", "高可用", "周报", "周末",
    "林数据库", "何接口", "马服务", "唐日志", "夏系统", "金数据", "白名单", "于今日", "任意",
    "沈阳", "武汉", "杭州", "南京", "用户中心", "认证中心", "生产环境", "测试环境", "数据中心",
    "系统服务", "项目管理", "数据库", "服务端", "接口文档", "开发环境", "测试数据", "操作系统",
})
TECHNICAL_PERSON_TERMS = frozenset({
    "日志", "系统", "接口", "项目", "数据", "服务", "缓存", "配置", "文档", "报告",
    "服务器", "数据库", "环境", "任务", "流程", "模块", "请求", "响应",
})
ORG_SUFFIXES = ("有限公司", "股份有限公司", "实验室", "研究院", "中心", "系统", "模块", "数据库", "服务", "数据", "科技")
LABEL_PATTERN = re.compile(
    r"(?:申请人|负责人|联系人|审核人|审批人|经办人|创建人|处理人|提交人|操作人|协助人|复核人|开发人员|"
    r"现场负责人|项目负责人|客户联系人|operator|owner|reviewer|approver|name)"
    r"\s*(?:[:：=]\s*|是\s*|为\s*)?$", re.I
)
DIRECT_PREFIX_PATTERN = re.compile(r"(?:请(?:先)?联系|联系|由|交给|找|问过|见到了|请)\s*$")
SUBJECT_VERBS = ("会继续处理", "继续处理", "继续反馈", "再确认", "已经沟通", "应该知道", "来自", "反馈", "确认", "表示", "负责", "提交", "审批", "处理", "排查", "回复", "联系", "创建", "协助", "沟通", "说", "到了", "没来")
TIME_WORDS = ("今天", "昨天", "随后", "已经", "正在", "再次")
CONNECTORS = frozenset("和与、及跟")
CONNECTOR_WORDS = ("和", "与", "、", "及", "跟", "还有")
GRAMMAR_PREFIX_CHARS = frozenset("再已会正")
NON_NAME_SUFFIX_CHARS = frozenset("了的呢吗啊吧")
ACTION_FRAGMENTS = ("再次", "已经", "正在", "随后", "今天", "昨天", "刚刚", "继续", "负责", "确认", "反馈", "处理", "提交", "联系")
# Chinese interrogative/function constructions beginning with the surname-like
# character 何.  A strong role/contact context deliberately overrides this.
FUNCTIONAL_HE_FOLLOWERS = frozenset("以时处故为必况人事种等")
THRESHOLD = 6


@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    text: str
    score: int
    strong: bool


class ChineseNameDetector:
    """Small explainable detector; it never edits text or accesses the network.

    Its confidence is a deterministic acceptance-strength marker, not a
    calibrated neural-model probability.
    """

    model_name = "person-lite"

    def recognize(self, text: str) -> list[EntityResult]:
        candidates = self._candidates(text)
        accepted = self._resolve(candidates)
        return [EntityResult("PERSON", item.start, item.end, item.text,
                             0.99 if item.strong else 0.90, self.model_name)
                for item in accepted]

    def _candidates(self, text: str) -> list[_Candidate]:
        raw: list[tuple[int, int, str]] = []
        for start in range(len(text)):
            for surname in COMPOUND_SURNAMES:
                raw.extend(self._names_after(text, start, surname))
            if text[start] in SURNAMES and not any(text.startswith(surname, start) for surname in COMPOUND_SURNAMES):
                raw.extend(self._names_after(text, start, text[start]))

        pair_spans = self._paired_spans(text, raw)
        candidates = []
        for start, end, value in raw:
            role_context = self._role_context(text, start)
            strong = self._strong_context(text, start, end, value)
            if self._blocked(text, start, end, value, role_context, strong):
                continue
            weak = self._weak_context(text, start, end)
            score = 2 + (4 if strong else 0) + (1 if weak else 0) + (4 if (start, end) in pair_spans else 0)
            if score >= THRESHOLD:
                candidates.append(_Candidate(start, end, value, score, strong))
        return candidates

    @staticmethod
    def _names_after(text: str, start: int, surname: str) -> list[tuple[int, int, str]]:
        if not text.startswith(surname, start):
            return []
        base = start + len(surname)
        rows = []
        for remainder_length in (1, 2):
            end = base + remainder_length
            if end <= len(text) and all(_is_cjk(character) for character in text[base:end]):
                rows.append((start, end, text[start:end]))
        return rows

    @staticmethod
    def _paired_spans(text: str, raw: list[tuple[int, int, str]]) -> set[tuple[int, int]]:
        paired = set()
        for left in raw:
            for right in raw:
                if left is right or left[1] > right[0]:
                    continue
                if (ChineseNameDetector._pair_left_has_boundary(text, left[0])
                        and text[left[1]:right[0]].strip() in CONNECTOR_WORDS
                        and ChineseNameDetector._pair_end_is_safe(text[right[1]:])):
                    paired.add((left[0], left[1]))
                    paired.add((right[0], right[1]))
        return paired

    def _strong_context(self, text: str, start: int, end: int, value: str) -> bool:
        after = text[end:end + 12]
        if self._role_context(text, start):
            return self._name_end_is_safe(after)
        if value[-1] not in GRAMMAR_PREFIX_CHARS and any(after.startswith(verb) for verb in SUBJECT_VERBS):
            return True
        return any(after.startswith(f"{time_word}{verb}") for time_word in TIME_WORDS for verb in SUBJECT_VERBS)

    @staticmethod
    def _role_context(text: str, start: int) -> bool:
        before = text[max(0, start - 20):start]
        return bool(LABEL_PATTERN.search(before) or DIRECT_PREFIX_PATTERN.search(before))

    def _weak_context(self, text: str, start: int, end: int) -> bool:
        before = text[max(0, start - 1):start]
        after = text[end:end + 3]
        return before in CONNECTORS or after[:1] in CONNECTORS or any(after.startswith(word) for word in TIME_WORDS)

    @staticmethod
    def _name_end_is_safe(after: str) -> bool:
        return (not after or not _is_cjk(after[0]) or any(after.startswith(word) for word in SUBJECT_VERBS + TIME_WORDS)
                or after[:1] in NON_NAME_SUFFIX_CHARS)

    @staticmethod
    def _pair_end_is_safe(after: str) -> bool:
        return not after or not _is_cjk(after[0]) or after.startswith(("在", "已经", "会", "再", "完成", "进行", "沟通", "协作", "讨论", "联系"))

    @staticmethod
    def _pair_left_has_boundary(text: str, start: int) -> bool:
        if start == 0 or not _is_cjk(text[start - 1]):
            return True
        before = text[max(0, start - 20):start]
        return bool(LABEL_PATTERN.search(before) or DIRECT_PREFIX_PATTERN.search(before))

    @staticmethod
    def _blocked(text: str, start: int, end: int, value: str,
                 role_context: bool, strong: bool) -> bool:
        if value in TECHNICAL_PERSON_TERMS and not role_context:
            return True
        if value[-1] in NON_NAME_SUFFIX_CHARS:
            return True
        if not role_context and value[0] == "何":
            # 何 may begin a name or an interrogative construction.  A preceding
            # 为 means this candidate starts inside 为何..., not at a lexical name
            # boundary.  Functional followers reject two-character grammar
            # phrases while still allowing a strong three-character subject such
            # as 何为民反馈问题.
            if start > 0 and text[start - 1] == "为":
                return True
            if (len(value) >= 2 and value[1] in FUNCTIONAL_HE_FOLLOWERS
                    and not (len(value) == 3 and strong)):
                return True
        if (start > 0 and _is_cjk(text[start - 1])
                and any(value[1:].startswith(fragment) for fragment in ACTION_FRAGMENTS)):
            return True
        word_start, word_end = start, end
        while word_start and _is_cjk(text[word_start - 1]):
            word_start -= 1
        while word_end < len(text) and _is_cjk(text[word_end]):
            word_end += 1
        word = text[word_start:word_end]
        if value in STOPWORDS or word in STOPWORDS:
            return True
        if any(text.startswith(stopword, start) for stopword in STOPWORDS):
            return True
        return any(text.startswith(suffix, end) for suffix in ORG_SUFFIXES)

    @staticmethod
    def _resolve(candidates: list[_Candidate]) -> list[_Candidate]:
        accepted: list[_Candidate] = []
        for candidate in sorted(candidates, key=lambda item: (-item.score, item.start, -(item.end - item.start))):
            if all(candidate.end <= kept.start or candidate.start >= kept.end for kept in accepted):
                accepted.append(candidate)
        return sorted(accepted, key=lambda item: item.start)


def _is_cjk(character: str) -> bool:
    return "\u4e00" <= character <= "\u9fff"
