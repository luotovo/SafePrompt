from __future__ import annotations

from dataclasses import dataclass
import re
import time
from collections.abc import Callable, Iterable

from .core import Finding, KNOWN_CATEGORIES


PLACEHOLDER = re.compile(r"<([A-Z][A-Z0-9_]*)_([1-9][0-9]*)>")


@dataclass(frozen=True)
class RestoreResult:
    text: str
    restored_count: int
    unknown_count: int


class ActiveRecoverySession:
    """One short-lived, memory-only placeholder mapping."""

    def __init__(self, ttl_seconds: float = 15 * 60, clock: Callable[[], float] = time.monotonic):
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._mapping: dict[str, str] = {}
        self._expires_at = 0.0

    @property
    def active(self) -> bool:
        if self._mapping and self.clock() >= self._expires_at:
            self.clear()
        return bool(self._mapping)

    def replace(self, findings: Iterable[Finding]) -> None:
        self._mapping = {item.replacement: item.original_value for item in findings
                         if item.selected and item.replacement}
        self._expires_at = self.clock() + self.ttl_seconds if self._mapping else 0.0

    def clear(self) -> None:
        self._mapping.clear()
        self._expires_at = 0.0

    def restore(self, text: str) -> RestoreResult:
        mapping = self._mapping if self.active else {}
        restored = unknown = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal restored, unknown
            placeholder = match.group()
            if match.group(1) not in KNOWN_CATEGORIES:
                return placeholder
            if placeholder not in mapping:
                unknown += 1
                return placeholder
            restored += 1
            return mapping[placeholder]

        return RestoreResult(PLACEHOLDER.sub(replace, text), restored, unknown)
