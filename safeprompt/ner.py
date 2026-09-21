from __future__ import annotations

from dataclasses import dataclass
import math
import re
from queue import Queue
from threading import Lock, Thread
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
# Thresholds are model-specific and remain empty until measured on the shared validation set.
MODEL_THRESHOLDS: dict[str, dict[str, float]] = {}


class NullRecognizer:
    """Offline no-op used until the model spike selects a concrete adapter."""

    def recognize(self, text: str) -> list[EntityResult]:
        return []


class NerService:
    """Lazily loads one local recognizer and degrades permanently for this session on failure."""

    def __init__(self, loader: Callable[[], EntityRecognizer], timeout_seconds: float = 2.0):
        self.loader = loader
        self.timeout_seconds = timeout_seconds
        self._recognizer: EntityRecognizer | None = None
        self._unavailable = False
        self._loading = False
        self._lock = Lock()
        self._requests: Queue[tuple[str, Queue[tuple[bool, object]]]] = Queue()

    @property
    def unavailable(self) -> bool:
        return self._unavailable

    @property
    def loading(self) -> bool:
        return self._loading

    def start_loading(self) -> bool:
        """Start the one-time model load without blocking the UI thread."""
        with self._lock:
            if self._recognizer is not None or self._unavailable or self._loading:
                return False
            self._loading = True

        def work() -> None:
            try:
                recognizer = self.loader()
            except Exception:
                self._unavailable = True
                self._loading = False
                return
            self._recognizer = recognizer
            self._loading = False
            while not self._unavailable:
                text, output = self._requests.get()
                try:
                    output.put((True, recognizer.recognize(text)))
                except Exception as error:
                    output.put((False, error))

        Thread(target=work, daemon=True).start()
        return True

    def recognize(self, text: str) -> list[EntityResult]:
        if self._unavailable:
            return []
        if self._recognizer is None:
            self.start_loading()
            return []
        output: Queue[tuple[bool, object]] = Queue(maxsize=1)

        self._requests.put((text, output))
        try:
            success, value = output.get(timeout=self.timeout_seconds)
        except Exception:
            self._unavailable = True
            return []
        if not success:
            self._unavailable = True
            return []
        return value  # type: ignore[return-value]

def to_findings(source_text: str, results: list[EntityResult],
                category_defaults: dict[str, bool] | None = None,
                thresholds_by_model: dict[str, dict[str, float]] | None = None) -> list[Finding]:
    thresholds_by_model = MODEL_THRESHOLDS | (thresholds_by_model or {})
    defaults = DEFAULT_SELECTED | (category_defaults or {})
    findings = []
    for result in results:
        category = result.category.upper()
        if category not in NER_CATEGORIES:
            continue
        if (not isinstance(result.start, int) or isinstance(result.start, bool)
                or not isinstance(result.end, int) or isinstance(result.end, bool)
                or not 0 <= result.start < result.end <= len(source_text)
                or source_text[result.start:result.end] != result.text):
            continue
        if (not isinstance(result.confidence, (int, float)) or isinstance(result.confidence, bool)
                or not math.isfinite(result.confidence) or not 0 <= result.confidence <= 1):
            continue
        threshold = thresholds_by_model.get(result.model, {}).get(category, 0.0)
        if result.confidence < threshold:
            continue
        findings.append(Finding(category, result.start, result.end, result.text, "entity_model",
                                RISK_LEVEL.get(category, "medium"), defaults.get(category, False), "",
                                f"{category}:{result.start}:{result.end}"))
    return _expand_same_entity_occurrences(source_text, findings)


def _expand_same_entity_occurrences(source_text: str, findings: list[Finding]) -> list[Finding]:
    """Add safe exact occurrences for model-recognized PERSON and ORG entities."""
    expanded = list(findings)
    seen = {(item.category, item.start, item.end) for item in findings}
    for seed in findings:
        if (seed.source != "entity_model" or seed.category not in EXPANDED_NER_CATEGORIES
                or _is_shadowed_by_longer_entity(seed, findings)):
            continue
        for match in re.finditer(re.escape(seed.original_value), source_text):
            start, end = match.span()
            key = (seed.category, start, end)
            if key in seen or not _safe_occurrence_boundary(source_text, start, end, seed):
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


def _safe_occurrence_boundary(text: str, start: int, end: int, seed: Finding) -> bool:
    """Avoid propagating an entity into an obvious longer same-text expression."""
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    if seed.category == "PERSON":
        return before != seed.original_value[0] and after != seed.original_value[-1]
    # A short organization embedded after a non-grammar Chinese prefix is usually a
    # fragment of a longer organization, e.g. 中国共产党中国地质大学（武汉）委员会.
    return not (_is_cjk(before) and before not in "在是与和向由到给为对从将把请")


def _is_cjk(character: str) -> bool:
    return "\u4e00" <= character <= "\u9fff"
