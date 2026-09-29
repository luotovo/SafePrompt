from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from typing import Iterable


RISK_LEVEL = {
    "DB_CREDENTIAL": "high", "PASSWORD": "high", "SECRET": "high", "API_KEY": "high",
    "TOKEN": "high", "ID_CARD": "high", "BANK_CARD": "high", "PHONE": "high", "EMAIL": "high",
    "URL": "medium", "IP": "medium", "DOMAIN": "medium", "PERSON": "medium",
    "CUSTOMER": "medium", "PROJECT": "medium", "DEPARTMENT": "low", "SYSTEM": "low",
    "ORG": "medium", "ID": "medium",
}
PRIORITY = {
    "DB_CREDENTIAL": 1, "PASSWORD": 2, "SECRET": 2, "API_KEY": 2, "TOKEN": 2,
    "ID_CARD": 3, "PHONE": 3, "EMAIL": 3, "BANK_CARD": 4, "URL": 4, "IP": 5, "DOMAIN": 5,
    "PERSON": 6, "ORG": 7, "CUSTOMER": 6, "PROJECT": 6, "DEPARTMENT": 6, "SYSTEM": 6, "ID": 6,
}
SOURCE_PRIORITY = {"rule": 1, "dictionary": 2, "entity_model": 3, "lightweight_person": 4}
RESERVED_PLACEHOLDER = re.compile(r"<[A-Z][A-Z0-9_]*_[0-9]+>")
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
    ("TOKEN", re.compile(
        r"\bBearer\s+(?P<bearer>[A-Za-z0-9._~+/=-]+)"
        r"|\"?(?:access[_ ]?token|refresh_token|token|访问令牌)\"?\s*(?:[:：=]|为)\s*"
        r"(?:[\"'`](?P<token_quoted>[^\"'`\r\n]*)[\"'`]|(?P<token_raw>[^\s,;，；}\]）】]+))"
        r"|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", re.I)),
    ("API_KEY", re.compile(
        r"\"?(?:api[_ -]?key)\"?\s*(?:[:：=]|为)\s*"
        r"(?:[\"'`](?P<api_quoted>[A-Za-z0-9._~-]{12,})[\"'`]|(?P<api_raw>[A-Za-z0-9._~-]{12,}))"
        r"|\b(?:sk|pk|ak|rk)_[A-Za-z0-9_-]{12,}\b", re.I)),
    ("PASSWORD", re.compile(
        r"\"?(?:password|passwd|pwd|数据库密码|登录密码|管理员密码|管理员口令|密码|口令)\"?\s*"
        r"(?:[:：=]|为)\s*(?:[\"'`](?P<password_quoted>[^\"'`\r\n]*)[\"'`]"
        r"|(?P<password_raw>[^\s,;，；}\]）】]+))", re.I)),
    ("SECRET", re.compile(r"\"?(?:secret|client_secret)\"?\s*[:=]\s*(?:[\"'](?P<quoted>[^\"'\r\n]*)[\"']|(?P<raw>[^\s,;，；}\]）】]+))", re.I)),
    ("ID", re.compile(
        r'(?<![A-Za-z0-9_])"?(?P<id_key>[iI][dD]|[A-Za-z][A-Za-z0-9_]*Id|[A-Za-z][A-Za-z0-9_]*_[iI][dD])"?\s*[:=]\s*'
        r'(?:"(?P<id_quoted>[A-Za-z0-9_-]{3,})"|(?P<id_raw>[A-Za-z0-9_-]{3,}))', re.I)),
    ("ID_CARD", re.compile(r"(?<!\d)\d{17}[\dXx](?![\dXx])")),
    ("BANK_CARD", re.compile(r"(?<!\d)\d{16,19}(?!\d)")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+86[- ]?)?1[3-9]\d{9}(?!\d)")),
    ("EMAIL", re.compile(
        r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])")),
    ("URL", re.compile(r"\bhttps?://[^\s'\"<>，。；）】]+", re.I)),
    ("IP", re.compile(r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])")),
    ("DOMAIN", re.compile(r"(?<![A-Za-z0-9.-])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?![A-Za-z0-9.-])")),
)


def detect(text: str, dictionary: Iterable[tuple] = (), category_defaults: dict[str, bool] | None = None,
           extra_candidates: Iterable[Finding] = ()) -> list[Finding]:
    """Return non-overlapping findings according to the PRD priority order."""
    candidates: list[Finding] = []
    for category, pattern in RULES:
        for match in pattern.finditer(text):
            start, end = _value_span(match)
            if category == "BANK_CARD" and not _luhn_valid(text[start:end]):
                continue
            if category == "DOMAIN" and not _domain_valid(text, start, end):
                continue
            if category == "ID" and (match.group("id_key").casefold() == "valid"
                                     or not any(character.isdigit() for character in text[start:end])):
                continue
            candidates.append(_finding(category, start, end, text[start:end], "rule", category_defaults))
    for match in re.finditer(r"(?<![0-9A-Fa-f:])[0-9A-Fa-f:]{2,}(?![0-9A-Fa-f:])", text):
        value = match.group()
        if ":" in value and _ipv6_valid(value):
            candidates.append(_finding("IP", match.start(), match.end(), value, "rule", category_defaults))
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
    reserved = set(RESERVED_PLACEHOLDER.findall(text))
    resolved: list[Finding] = []
    for item in sorted(findings, key=lambda finding: finding.start):
        key = (item.category, item.original_value.casefold())
        if item.selected and key not in replacements:
            number = counters.get(item.category, 0)
            while True:
                number += 1
                replacement = f"<{item.category}_{number}>"
                if replacement not in reserved:
                    break
            counters[item.category] = number
            replacements[key] = replacement
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
    for name in ("bearer", "quoted", "raw", "token_quoted", "token_raw", "api_quoted", "api_raw",
                 "password_quoted", "password_raw", "id_quoted", "id_raw"):
        if match.groupdict().get(name) is not None:
            return match.span(name)
    return match.span()


def _dictionary_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if term.isascii() and re.fullmatch(r"[A-Za-z0-9_]+", term):
        return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.I)
    return re.compile(escaped, re.I)


def _luhn_valid(value: str) -> bool:
    digits = [int(character) for character in value]
    parity = len(digits) % 2
    total = 0
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _ipv6_valid(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 6
    except ValueError:
        return False


def _domain_valid(text: str, start: int, end: int) -> bool:
    value = text[start:end]
    labels = value.casefold().split(".")
    common_suffixes = {"com", "net", "org", "cn", "io", "co", "edu", "gov", "dev", "ai"}
    before = text[max(0, start - 16):start]
    explicit_context = bool(re.search(r"(?:域名|domain|host)\s*(?:[:：=]|为)\s*$", before, re.I))
    return ((len(labels) >= 3 or explicit_context) and labels[-1] in common_suffixes
            and all(label and len(label) <= 63 and not label.startswith("-") and not label.endswith("-")
                    for label in labels))


def _resolve_overlaps(candidates: list[Finding]) -> list[Finding]:
    ranked = sorted(candidates, key=lambda item: (
        PRIORITY.get(item.category, 7),
        -(item.end - item.start) if item.category == "PERSON" else 0,
        SOURCE_PRIORITY.get(item.source, 9), -(item.end - item.start), item.start,
        0 if item.source == "entity_model" and item.category == "ORG" else 1,
    ))
    accepted: list[Finding] = []
    for item in ranked:
        if all(item.end <= kept.start or item.start >= kept.end for kept in accepted):
            accepted.append(item)
    return sorted(accepted, key=lambda item: item.start)
