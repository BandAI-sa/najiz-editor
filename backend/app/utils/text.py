from __future__ import annotations

import re
from datetime import date


TOKEN_PATTERN = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)
DATE_PATTERNS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text or "")]


def chunk_text(text: str, chunk_size: int = 160) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    current = []
    current_length = 0
    for paragraph in text.splitlines(keepends=True):
        if current_length + len(paragraph) > chunk_size and current:
            chunks.append("".join(current))
            current = [paragraph]
            current_length = len(paragraph)
        else:
            current.append(paragraph)
            current_length += len(paragraph)
    if current:
        chunks.append("".join(current))
    return chunks


def parse_number(value: str) -> int | None:
    digits = re.sub(r"[^\d]", "", value or "")
    return int(digits) if digits else None


def parse_date(value: str) -> date | None:
    from datetime import datetime

    for pattern in DATE_PATTERNS:
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
    return None
