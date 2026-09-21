from __future__ import annotations

from dataclasses import dataclass
import math
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

        def load() -> None:
            try:
                recognizer = self.loader()
            except Exception:
                self._unavailable = True
            else:
                self._recognizer = recognizer
            finally:
                self._loading = False

        Thread(target=load, daemon=True).start()
        return True

    def recognize(self, text: str) -> list[EntityResult]:
        if self._unavailable:
            return []
        if self._recognizer is None:
            self.start_loading()
            return []
        output: Queue[tuple[bool, object]] = Queue(maxsize=1)

        def run() -> None:
            try:
                output.put((True, self._recognizer.recognize(text)))
            except Exception as error:
                output.put((False, error))

        Thread(target=run, daemon=True).start()
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
    return findings
