"""Tests for the remoteok normalizer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from job_alert.sources import strip_html as _strip_html
from job_alert.sources.remoteok import _normalize


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, ""),
        ("", ""),
        ("<p>hello</p>", "hello"),
        ("&amp; &lt;tag&gt;", "& <tag>"),
        ("<p>a</p>\n\n<p>b</p>", "a b"),
    ],
)
def test_strip_html(raw: str | None, expected: str) -> None:
    assert _strip_html(raw) == expected


def _sample_item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "abc123",
        "url": "https://remoteok.com/remote-jobs/example",
        "position": "  Software Engineer  ",
        "company": "Acme Corp",
        "location": "  ",
        "epoch": int(datetime(2026, 5, 20, tzinfo=timezone.utc).timestamp()),
        "description": "<p>Build things</p>",
        "tags": ["python", "remote", "backend"],
    }
    base.update(overrides)
    return base


def test_normalize_happy_path() -> None:
    result = _normalize(_sample_item())
    assert result is not None
    assert result["source"] == "remoteok"
    assert result["url"] == "https://remoteok.com/remote-jobs/example"
    assert result["title"] == "Software Engineer"
    assert result["company"] == "Acme Corp"
    assert result["location"] == "Worldwide remote", "blank location must default"
    assert result["posted_date"] == "2026-05-20"
    desc = result["raw_description"]
    assert isinstance(desc, str)
    assert desc.startswith("Tags: python, remote, backend")
    assert "Build things" in desc


def test_normalize_keeps_explicit_location() -> None:
    result = _normalize(_sample_item(location="EU only"))
    assert result is not None
    assert result["location"] == "EU only"


def test_normalize_without_tags_omits_prefix() -> None:
    result = _normalize(_sample_item(tags=[]))
    assert result is not None
    desc = result["raw_description"]
    assert isinstance(desc, str)
    assert "Tags:" not in desc
    assert desc == "Build things"


def test_normalize_without_epoch_yields_none_date() -> None:
    item = _sample_item()
    item.pop("epoch")
    result = _normalize(item)
    assert result is not None
    assert result["posted_date"] is None


def test_normalize_drops_missing_url() -> None:
    item = _sample_item()
    item.pop("url")
    assert _normalize(item) is None


def test_normalize_drops_missing_title() -> None:
    assert _normalize(_sample_item(position="")) is None
