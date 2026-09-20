from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


RISK_LEVEL = {
    "DB_CREDENTIAL": "high", "PASSWORD": "high", "SECRET": "high", "API_KEY": "high",
    "TOKEN": "high", "ID_CARD": "high", "PHONE": "high", "EMAIL": "high",
    "URL": "medium", "IP": "medium", "DOMAIN": "medium", "PERSON": "medium",
    "CUSTOMER": "medium", "PROJECT": "medium", "DEPARTMENT": "low", "SYSTEM": "low",
    "ORG": "medium",
}
PRIORITY = {
    "DB_CREDENTIAL": 1, "PASSWORD": 2, "SECRET": 2, "API_KEY": 2, "TOKEN": 2,
    "ID_CARD": 3, "PHONE": 3, "EMAIL": 3, "URL": 4, "IP": 5, "DOMAIN": 5,
    "PERSON": 6, "ORG": 6, "CUSTOMER": 6, "PROJECT": 6, "DEPARTMENT": 6, "SYSTEM": 6,
}
SOURCE_PRIORITY = {"rule": 1, "dictionary": 2, "entity_model": 3}
DEFAULT_SELECTED = {category: True for category in RISK_LEVEL}
DEFAULT_SELECTED.update({"DEPARTMENT": False, "SYSTEM": False, "TABLE_NAME": False, "FIELD_NAME": False})
KNOWN_CATEGORIES = frozenset(DEFAULT_SELECTED)


@dataclass(frozen=True)
class Finding:
    category: str
    start: int
    end: int
    original_value: str
    source: str
    risk_level: str
    selected: bool = True
    replacement: str = ""
    id: str = ""

    def with_replacement(self, replacement: str) -> "Finding":
        return Finding(self.category, self.start, self.end, self.original_value, self.source,
                       self.risk_level, self.selected, replacement, self.id)


RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DB_CREDENTIAL", re.compile(r"\b(?:jdbc:[a-z0-9]+|(?:mysql|postgres(?:ql)?|mssql)://)[^\s'\"<>，。；）】]+", re.I)),
    ("TOKEN", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", re.I)),
    ("API_KEY", re.compile(r"\b(?:sk|pk|ak|rk)_[A-Za-z0-9_-]{12,}\b", re.I)),
    ("PASSWORD", re.compile(r"\"?(?:password|passwd|pwd)\"?\s*[:=]\s*(?:[\"'](?P<quoted>[^\"'\r\n]*)[\"']|(?P<raw>[^\s,;，；}\]）】]+))", re.I)),
    ("SECRET", re.compile(r"\"?(?:secret|client_secret)\"?\s*[:=]\s*(?:[\"'](?P<quoted>[^\"'\r\n]*)[\"']|(?P<raw>[^\s,;，；}\]）】]+))", re.I)),
    ("ID_CARD", re.compile(r"\b\d{17}[\dXx]\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+86[- ]?)?1[3-9]\d{9}(?!\d)")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("URL", re.compile(r"\bhttps?://[^\s'\"<>，。；）】]+", re.I)),
    ("IP", re.compile(r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])")),
    ("DOMAIN", re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b")),
)


def detect(text: str, dictionary: Iterable[tuple] = (), category_defaults: dict[str, bool] | None = None,
           extra_candidates: Iterable[Finding] = ()) -> list[Finding]:
    """Return non-overlapping findings according to the PRD priority order."""
    candidates: list[Finding] = []
    for category, pattern in RULES:
        for match in pattern.finditer(text):
            start, end = _value_span(match)
            candidates.append(_finding(category, start, end, text[start:end], "rule", category_defaults))
    for entry in sorted(dictionary, key=lambda item: len(item[0]), reverse=True):
        term, category = entry[:2]
        term_selected = entry[2] if len(entry) > 2 else None
        if not term:
            continue
        pattern = _dictionary_pattern(term)
        for match in pattern.finditer(text):
            candidates.append(_finding(category.upper(), match.start(), match.end(), match.group(), "dictionary",
                                       category_defaults, term_selected))
    candidates.extend(extra_candidates)
    return _resolve_overlaps(candidates)


def mask(text: str, findings: Iterable[Finding]) -> tuple[str, list[Finding]]:
    """Apply selected findings, assigning per-category numbers by first occurrence."""
    counters: dict[str, int] = {}
    replacements: dict[tuple[str, str], str] = {}
    resolved: list[Finding] = []
    for item in sorted(findings, key=lambda finding: finding.start):
        key = (item.category, item.original_value.casefold())
        if item.selected and key not in replacements:
            counters[item.category] = counters.get(item.category, 0) + 1
            replacements[key] = f"<{item.category}_{counters[item.category]}>"
        resolved.append(item.with_replacement(replacements.get(key, "")))
    chunks: list[str] = []
    cursor = 0
    for item in resolved:
        chunks.append(text[cursor:item.start])
        chunks.append(item.replacement if item.selected else item.original_value)
        cursor = item.end
    chunks.append(text[cursor:])
    return "".join(chunks), resolved


def _finding(category: str, start: int, end: int, value: str, source: str,
             category_defaults: dict[str, bool] | None = None, selected_override: bool | None = None) -> Finding:
    selected = selected_override if selected_override is not None else (category_defaults or {}).get(
        category, DEFAULT_SELECTED.get(category, False))
    return Finding(category, start, end, value, source, RISK_LEVEL.get(category, "low"),
                   selected, "", f"{category}:{start}:{end}")


def _value_span(match: re.Match[str]) -> tuple[int, int]:
    """Field rules capture only their secret value; other rules use the full match."""
    for name in ("quoted", "raw"):
        if match.groupdict().get(name) is not None:
            return match.span(name)
    return match.span()


def _dictionary_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if term.isascii() and re.fullmatch(r"[A-Za-z0-9_]+", term):
        return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.I)
    return re.compile(escaped, re.I)


def _resolve_overlaps(candidates: list[Finding]) -> list[Finding]:
    ranked = sorted(candidates, key=lambda item: (
        PRIORITY.get(item.category, 7), SOURCE_PRIORITY.get(item.source, 9),
        -(item.end - item.start), item.start,
    ))
    accepted: list[Finding] = []
    for item in ranked:
        if all(item.end <= kept.start or item.start >= kept.end for kept in accepted):
            accepted.append(item)
    return sorted(accepted, key=lambda item: item.start)
