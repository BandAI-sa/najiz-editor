from __future__ import annotations

import re


DEFAULT_PETITION_ROLE = "principal"
PETITION_ROLE_META_KEY = "petition_role"
PETITION_ROLE_LABELS = {
    "principal": "أصيل",
    "agent": "وكيل",
}

_SELF_REFERENCE_PATTERNS = (
    re.compile(r"(?:بصفتي|بوصفي)\s+محام(?:ي|يا|ياً|يًا)?(?:\s+سعود(?:ي|يا|ياً|يًا)?)?[،,:؛-]*\s*", re.UNICODE),
    re.compile(r"أنا\s+محام(?:ي|يا|ياً|يًا)?(?:\s+سعود(?:ي|يا|ياً|يًا)?)?[،,:؛-]*\s*", re.UNICODE),
    re.compile(r"كمحام(?:ي|يا|ياً|يًا)?(?:\s+سعود(?:ي|يا|ياً|يًا)?)?[،,:؛-]*\s*", re.UNICODE),
)


def normalize_petition_role(role: str | None) -> str:
    normalized = (role or "").strip().lower()
    if normalized in PETITION_ROLE_LABELS:
        return normalized
    return DEFAULT_PETITION_ROLE


def petition_role_label(role: str | None) -> str:
    normalized = normalize_petition_role(role)
    return PETITION_ROLE_LABELS[normalized]


def sanitize_petition_text(text: str) -> str:
    sanitized = (text or "").strip()
    if not sanitized:
        return sanitized

    for pattern in _SELF_REFERENCE_PATTERNS:
        sanitized = pattern.sub("", sanitized)

    sanitized = re.sub(r"^[\s،,:؛-]+", "", sanitized, flags=re.MULTILINE)
    sanitized = re.sub(r"[ \t]{2,}", " ", sanitized)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
    return sanitized.strip()
