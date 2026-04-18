from __future__ import annotations

import re
from html import unescape

import markdown


MARKDOWN_EXTENSIONS = ["extra", "nl2br", "sane_lists"]
TAG_PATTERN = re.compile(r"<[^>]+>")
SEPARATOR_PATTERN = re.compile(r"(?m)^[=\-]{3,}$")


def render_markdown_html(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS, output_format="html5")


def strip_markdown_text(value: str) -> str:
    rendered = render_markdown_html(value)
    if not rendered:
        text = value or ""
    else:
        text = TAG_PATTERN.sub(" ", rendered)
        text = unescape(text)
    text = SEPARATOR_PATTERN.sub(" ", text)
    return " ".join(text.split())
