"""Helpers compartidos por los scrapers de fuentes de jobs."""

from __future__ import annotations

import re
from html import unescape


def strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return unescape(text).strip()
