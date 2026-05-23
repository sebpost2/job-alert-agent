"""Tests for the getonboard normalizer and HTML scrubber.

The normalizer is the contract boundary between the scraper and the rest of
the pipeline: every row in the `jobs` table is built from its output, so
silent shape changes propagate everywhere.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from job_alert.sources.getonboard import _normalize, _strip_html


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, ""),
        ("", ""),
        ("plain text", "plain text"),
        ("<p>hello <b>world</b></p>", "hello world"),
        ("<div>line1<br>line2</div>", "line1 line2"),
        ("&amp; &lt;tag&gt; &quot;x&quot;", '& <tag> "x"'),
        ("  <p>  spaced  </p>  ", "spaced"),
        ("<p>line1</p>\n\n<p>line2</p>", "line1 line2"),
    ],
)
def test_strip_html(raw: str | None, expected: str) -> None:
    assert _strip_html(raw) == expected


def _sample_item(**overrides: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "title": "  Python Engineer  ",
        "description": "<p>Build things</p>",
        "functions": "<p>Write code</p>",
        "desirable": "",
        "benefits": "<p>Remote work</p>",
        "remote": True,
        "countries": [],
        "published_at": int(
            datetime(2026, 5, 20, tzinfo=timezone.utc).timestamp()
        ),
        "company": {"data": {"attributes": {"name": "Acme Corp"}}},
    }
    attrs.update(overrides)
    return {
        "links": {"public_url": "https://www.getonbrd.com/jobs/example"},
        "attributes": attrs,
    }


def test_normalize_happy_path() -> None:
    result = _normalize(_sample_item())
    assert result is not None
    assert result["source"] == "getonboard"
    assert result["url"] == "https://www.getonbrd.com/jobs/example"
    assert result["title"] == "Python Engineer"
    assert result["company"] == "Acme Corp"
    assert result["location"] == "Remote"
    assert result["posted_date"] == "2026-05-20"
    desc = result["raw_description"]
    assert isinstance(desc, str)
    assert "Build things" in desc and "Remote work" in desc
    assert "Write code" in desc


def test_normalize_remote_with_specific_countries() -> None:
    result = _normalize(_sample_item(remote=True, countries=["Peru", "Mexico"]))
    assert result is not None
    assert result["location"] == "Remote (Peru, Mexico)"


def test_normalize_onsite_uses_countries_as_location() -> None:
    result = _normalize(_sample_item(remote=False, countries=["Chile"]))
    assert result is not None
    assert result["location"] == "Chile"


def test_normalize_onsite_without_countries_is_none_location() -> None:
    result = _normalize(_sample_item(remote=False, countries=[]))
    assert result is not None
    assert result["location"] is None


def test_normalize_drops_missing_title() -> None:
    item = _sample_item(title="")
    assert _normalize(item) is None


def test_normalize_drops_missing_url() -> None:
    item = _sample_item()
    item["links"] = {}
    assert _normalize(item) is None


def test_normalize_handles_missing_company() -> None:
    item = _sample_item()
    item["attributes"]["company"] = None
    result = _normalize(item)
    assert result is not None
    assert result["company"] is None


def test_normalize_handles_malformed_item_returns_none() -> None:
    # No `attributes` key at all → KeyError path → None.
    assert _normalize({"links": {"public_url": "x"}}) is None
