from __future__ import annotations

from dataclasses import dataclass
import math
import re
from queue import Empty, Queue
from threading import Event, Lock, Thread
import time
from typing import Callable, Protocol

from .core import DEFAULT_SELECTED, Finding, RISK_LEVEL


@dataclass(frozen=True)
class EntityResult:
    category: str
    start: int
    end: int
    text: str
    confidence: float | None
    model: str


class EntityRecognizer(Protocol):
    def recognize(self, text: str) -> list[EntityResult]: ...


NER_CATEGORIES = frozenset({"PERSON", "ORG"})
EXPANDED_NER_CATEGORIES = frozenset({"PERSON", "ORG"})
EXPANDED_ENTITY_SOURCES = frozenset({"entity_model", "lightweight_person"})
ORG_LEGAL_CONTINUATION = re.compile(
    r"^[\u4e00-\u9fff]{0,12}(?:有限责任公司|股份有限公司|有限公司)"
)
# Thresholds are model-specific and remain empty until measured on the shared validation set.
MODEL_THRESHOLDS: dict[str, dict[str, float]] = {}
TECHNICAL_PERSON_TERMS = frozenset({
    "日志", "系统", "接口", "项目", "数据", "服务", "缓存", "配置", "文档", "报告",
    "服务器", "数据库", "环境", "任务", "流程", "模块", "请求", "响应",
})
PERSON_ORG_SUFFIXES = ("有限责任公司", "股份有限公司", "有限公司", "实验室", "研究院", "数据中心", "研发中心")
STRONG_PERSON_LABEL = re.compile(
    r"(?:负责人|项目负责人|联系人|审核人|审批人|申请人|开发人员|operator|owner|reviewer|approver|name)"
    r"\s*(?:[:：=]\s*|是\s*|为\s*)?$", re.I)


class NullRecognizer:
    """Offline no-op used until the model spike selects a concrete adapter."""

    def recognize(self, text: str) -> list[EntityResult]:
        return []


class NerService:
    """Lazily loads one local recognizer and degrades permanently for this session on failure."""

    def __init__(self, loader: Callable[[], EntityRecognizer], timeout_seconds: float | None = None):
        self.loader = loader
        self.timeout_seconds = timeout_seconds
        self._recognizer: EntityRecognizer | None = None
        self._unavailable = False
        self._loading = False
        self._lock = Lock()
        self._ready = Event()
        self._failure_reason: str | None = None
        self._ready_at: float | None = None
        self._requests: Queue[tuple[str, Queue[tuple[bool, object]]]] = Queue()

    @property
    def unavailable(self) -> bool:
        return self._unavailable

    @property
    def loading(self) -> bool:
        return self._loading

    @property
    def state(self) -> str:
        if self._unavailable:
            return "FAILED"
        if self._recognizer is not None:
            return "READY"
        if self._loading:
            return "LOADING"
        return "NOT_STARTED"

    @property
    def failure_reason(self) -> str | None:
        return self._failure_reason

    @property
    def ready_at(self) -> float | None:
        return self._ready_at

    def start_loading(self) -> bool:
        """Start the one-time model load without blocking the UI thread."""
        with self._lock:
            if self._recognizer is not None or self._unavailable or self._loading:
                return False
            self._loading = True

        def work() -> None:
            try:
                recognizer = self.loader()
            except Exception as error:
                with self._lock:
                    self._failure_reason = f"{type(error).__name__}: {error}"
                    self._unavailable = True
                    self._loading = False
                    self._ready.set()
                return
            with self._lock:
                self._recognizer = recognizer
                self._ready_at = time.monotonic()
                self._loading = False
                self._ready.set()
            while not self._unavailable:
                text, output = self._requests.get()
                try:
                    output.put((True, recognizer.recognize(text)))
                except Exception as error:
                    self._failure_reason = f"{type(error).__name__}: {error}"
                    self._unavailable = True
                    output.put((False, error))

        Thread(target=work, daemon=True).start()
        return True

    def recognize(self, text: str, wait_for_ready: bool = False) -> list[EntityResult]:
        if self._unavailable:
            return []
        self.start_loading()
        if not self._ready.is_set() and not wait_for_ready:
            return []
        if not self._ready.wait(timeout=self.timeout_seconds):
            return []
        if self._unavailable or self._recognizer is None:
            return []
        output: Queue[tuple[bool, object]] = Queue(maxsize=1)

        self._requests.put((text, output))
        try:
            success, value = output.get(timeout=self.timeout_seconds)
        except Empty:
            return []
        if not success:
            return []
        return value  # type: ignore[return-value]

def to_findings(source_text: str, results: list[EntityResult],
                category_defaults: dict[str, bool] | None = None,
                thresholds_by_model: dict[str, dict[str, float]] | None = None,
                source: str = "entity_model") -> list[Finding]:
    thresholds_by_model = MODEL_THRESHOLDS | (thresholds_by_model or {})
    defaults = DEFAULT_SELECTED | (category_defaults or {})
    findings = []
    for original_result in results:
        split_results = _split_whitespace_person(original_result)
        for result in split_results:
            _append_finding(findings, source_text, result, defaults, thresholds_by_model, source)
    findings.extend(_contextual_three_character_he_names(source_text, findings, defaults, source))
    return _expand_same_entity_occurrences(source_text, findings)


def _append_finding(findings: list[Finding], source_text: str, result: EntityResult,
                    defaults: dict[str, bool], thresholds_by_model: dict[str, dict[str, float]],
                    source: str) -> None:
    category = result.category.upper()
    if category not in NER_CATEGORIES:
        return
    if (not isinstance(result.start, int) or isinstance(result.start, bool)
            or not isinstance(result.end, int) or isinstance(result.end, bool)
            or not 0 <= result.start < result.end <= len(source_text)
            or source_text[result.start:result.end] != result.text):
        return
    if (category == "PERSON" and result.text in TECHNICAL_PERSON_TERMS
            and not STRONG_PERSON_LABEL.search(source_text[max(0, result.start - 24):result.start])):
        return
    if category == "PERSON" and result.text.endswith(PERSON_ORG_SUFFIXES):
        return
    if (not isinstance(result.confidence, (int, float)) or isinstance(result.confidence, bool)
            or not math.isfinite(result.confidence) or not 0 <= result.confidence <= 1):
        return
    threshold = thresholds_by_model.get(result.model, {}).get(category, 0.0)
    if result.confidence < threshold:
        return
    findings.append(Finding(category, result.start, result.end, result.text, source,
                            RISK_LEVEL.get(category, "medium"), defaults.get(category, False), "",
                            f"{category}:{result.start}:{result.end}"))


def _split_whitespace_person(result: EntityResult) -> list[EntityResult]:
    """Split a model span that accidentally joins adjacent names across whitespace."""
    if result.category.upper() != "PERSON" or not any(char.isspace() for char in result.text):
        return [result]
    return [EntityResult(result.category, result.start + match.start(), result.start + match.end(),
                         match.group(), result.confidence, result.model)
            for match in re.finditer(r"\S+", result.text)]


def _contextual_three_character_he_names(source_text: str, findings: list[Finding],
                                         defaults: dict[str, bool], source: str) -> list[Finding]:
    """Recover an unambiguous three-character 何-name before a person action verb.

    UIE Nano's grammar guard correctly rejects 何人/何事/何为 questions, but can
    also omit a real three-character name such as 何为民.  Requiring exactly two
    name characters plus a person-action verb keeps those functional forms out.
    """
    if source != "entity_model":
        return []
    additions = []
    pattern = re.compile(r"(?<![\u4e00-\u9fff])(何[\u4e00-\u9fff]{2})(?=反馈|联系|负责|提交|确认|处理|回复)")
    for match in pattern.finditer(source_text):
        start, end = match.span(1)
        if any(not (end <= item.start or start >= item.end) for item in findings):
            continue
        additions.append(Finding("PERSON", start, end, match.group(1), source, RISK_LEVEL["PERSON"],
                                 defaults.get("PERSON", False), "", f"PERSON:{start}:{end}"))
    return additions


def _expand_same_entity_occurrences(source_text: str, findings: list[Finding]) -> list[Finding]:
    """Add safe exact occurrences for model-recognized PERSON and ORG entities."""
    expanded = list(findings)
    seen = {(item.category, item.start, item.end) for item in findings}
    for seed in findings:
        if (seed.source not in EXPANDED_ENTITY_SOURCES or seed.category not in EXPANDED_NER_CATEGORIES
                or _is_shadowed_by_longer_entity(seed, findings)):
            continue
        for match in re.finditer(re.escape(seed.original_value), source_text):
            start, end = match.span()
            key = (seed.category, start, end)
            if (key in seen or _target_is_shadowed_by_longer_entity(seed.category, start, end, findings)
                    or not _safe_occurrence_boundary(source_text, start, end, seed)):
                continue
            seen.add(key)
            expanded.append(Finding(seed.category, start, end, seed.original_value, seed.source,
                                    seed.risk_level, seed.selected, "", f"{seed.category}:{start}:{end}"))
    return expanded


def _is_shadowed_by_longer_entity(seed: Finding, findings: list[Finding]) -> bool:
    return any(other.category == seed.category and other != seed
               and other.start <= seed.start and seed.end <= other.end
               and (other.end - other.start) > (seed.end - seed.start)
               for other in findings)


def _target_is_shadowed_by_longer_entity(category: str, start: int, end: int, findings: list[Finding]) -> bool:
    """Do not propagate a short entity into a locally recognized longer entity."""
    return any(other.category == category and other.start <= start and end <= other.end
               and (other.end - other.start) > (end - start) for other in findings)


def _safe_occurrence_boundary(text: str, start: int, end: int, seed: Finding) -> bool:
    """Avoid propagating an entity into an obvious longer same-text expression."""
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    if seed.category == "PERSON":
        return (before != seed.original_value[0] and after != seed.original_value[-1]
                and not ORG_LEGAL_CONTINUATION.match(text[end:end + 20]))
    # A short organization embedded after a non-grammar Chinese prefix is usually a
    # fragment of a longer organization, e.g. 中国共产党中国地质大学（武汉）委员会.
    return not (_is_cjk(before) and before not in "在是与和向由到给为对从将把请")


def _is_cjk(character: str) -> bool:
    return "\u4e00" <= character <= "\u9fff"
