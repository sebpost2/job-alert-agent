"""Pure tests for Notion property builder (no HTTP calls).

`_properties_for` is the schema-mapping boundary: if its shape drifts, every
sync request returns 400 from Notion. Worth covering the verdict/select edge
cases and the truncation guard.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from job_alert.notion_sync import _properties_for


def _base_job(**overrides: Any) -> dict[str, Any]:
    job: dict[str, Any] = {
        "title": "Senior Engineer",
        "company": "Acme Corp",
        "url": "https://example.com/job/1",
        "fit_score": 80,
        "verdict": "fit",
        "reason": "Stack matches and remote OK",
        "source": "getonboard",
        "posted_date": date(2026, 5, 20),
    }
    job.update(overrides)
    return job


def test_properties_happy_path() -> None:
    props = _properties_for(_base_job())

    assert props["Title"]["title"][0]["text"]["content"] == "Senior Engineer"
    assert props["Company"]["rich_text"][0]["text"]["content"] == "Acme Corp"
    assert props["URL"]["url"] == "https://example.com/job/1"
    assert props["Fit Score"]["number"] == 80
    assert props["Verdict"]["select"]["name"] == "fit"
    assert props["Reason"]["rich_text"][0]["text"]["content"] == (
        "Stack matches and remote OK"
    )
    assert props["Source"]["select"]["name"] == "getonboard"
    assert props["Posted"]["date"]["start"] == "2026-05-20"


def test_properties_unknown_verdict_clears_select() -> None:
    """If the verdict is anything outside fit/stretch/skip, Notion must get
    a null select instead of an invalid option name."""
    props = _properties_for(_base_job(verdict="unknown"))
    assert props["Verdict"] == {"select": None}


def test_properties_missing_optional_fields() -> None:
    job = _base_job(
        company=None,
        reason=None,
        verdict=None,
        source=None,
        posted_date=None,
        fit_score=None,
        title=None,
    )
    props = _properties_for(job)
    # Empty strings are valid Notion rich_text content.
    assert props["Company"]["rich_text"][0]["text"]["content"] == ""
    assert props["Reason"]["rich_text"][0]["text"]["content"] == ""
    assert props["Verdict"] == {"select": None}
    assert props["Source"] == {"select": None}
    assert props["Posted"] == {"date": None}
    assert props["Fit Score"]["number"] is None
    # Title is required by Notion; the builder falls back to a placeholder.
    assert props["Title"]["title"][0]["text"]["content"] == "(sin título)"


def test_properties_truncate_long_fields() -> None:
    long_text = "x" * 5000
    props = _properties_for(_base_job(company=long_text, reason=long_text, title=long_text))
    assert len(props["Company"]["rich_text"][0]["text"]["content"]) == 2000
    assert len(props["Reason"]["rich_text"][0]["text"]["content"]) == 2000
    assert len(props["Title"]["title"][0]["text"]["content"]) == 2000
