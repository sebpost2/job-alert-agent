"""Tests for the Telegram digest formatter (no network).

Telegram with parse_mode=HTML breaks if `< > &` are not escaped in user-controlled
fields like company name or reason. These tests pin that contract.
"""

from __future__ import annotations

from typing import Any

from job_alert.telegram_digest import _esc, _format_message


def test_esc_handles_none_and_special_chars() -> None:
    assert _esc("") == ""
    assert _esc("R&D <team>") == "R&amp;D &lt;team&gt;"


def test_format_empty_jobs_returns_no_fits_message() -> None:
    msg = _format_message([])
    assert "No new fits today" in msg
    assert "<b>" in msg


def test_format_includes_all_fields_and_escapes_unsafe() -> None:
    jobs: list[dict[str, Any]] = [
        {
            "title": "Python <Engineer>",
            "company": "Acme & Co",
            "location": "Remote",
            "fit_score": 90,
            "reason": "Stack matches & remote OK",
            "source": "getonboard",
            "url": "https://example.com/job/1",
        }
    ]
    msg = _format_message(jobs)

    # Text fields must be HTML-escaped...
    assert "Python &lt;Engineer&gt;" in msg
    assert "Acme &amp; Co" in msg
    assert "Stack matches &amp; remote OK" in msg
    # ...but the URL must stay raw inside href.
    assert 'href="https://example.com/job/1"' in msg
    assert "<code>90/100</code>" in msg
    assert "top 1 fit(s)" in msg


def test_format_truncates_long_title() -> None:
    jobs: list[dict[str, Any]] = [
        {
            "title": "x" * 500,
            "company": "Acme",
            "location": "Remote",
            "fit_score": 80,
            "reason": "ok",
            "source": "getonboard",
            "url": "https://example.com/job/1",
        }
    ]
    msg = _format_message(jobs)
    # Title is sliced to 100 chars before escaping; "x" never needs escaping so
    # the rendered chunk is exactly 100 chars.
    assert "x" * 100 in msg
    assert "x" * 101 not in msg


def test_format_numbers_multiple_jobs() -> None:
    jobs: list[dict[str, Any]] = [
        {
            "title": f"Role {i}",
            "company": "Co",
            "location": "Remote",
            "fit_score": 70 + i,
            "reason": "r",
            "source": "remoteok",
            "url": f"https://example.com/{i}",
        }
        for i in range(3)
    ]
    msg = _format_message(jobs)
    assert "1. Role 0" in msg
    assert "2. Role 1" in msg
    assert "3. Role 2" in msg
