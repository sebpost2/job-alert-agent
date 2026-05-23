"""Tests for the data-quality checker.

Build a Parquet snapshot with a known mix of valid + invalid rows, then assert
that `check_parquet` finds the exact problems and `render_report` formats them
in a navigable way.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from job_alert.analytics.export import rows_to_parquet
from job_alert.analytics.quality import (
    QualityReport,
    RowError,
    check_parquet,
    render_report,
)


UTC_TS = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 1,
        "source": "getonboard",
        "url": "https://example.com/x",
        "title": "Backend",
        "company": "Acme",
        "location": "Lima",
        "posted_date": date(2025, 1, 1),
        "raw_description": None,
        "fit_score": None,
        "verdict": None,
        "reason": None,
        "scored_at": None,
        "notified_at": None,
        "created_at": UTC_TS,
    }
    row.update(overrides)
    return row


def test_check_all_valid(tmp_path: Path) -> None:
    rows = [_row(id=1), _row(id=2, url="https://example.com/y")]
    out = tmp_path / "ok.parquet"
    rows_to_parquet(rows, out)

    report = check_parquet(out)
    assert report.total == 2
    assert report.valid == 2
    assert report.invalid == 0
    assert report.all_valid is True
    assert report.errors == []


def test_check_flags_partial_scoring(tmp_path: Path) -> None:
    rows = [
        _row(id=1, fit_score=50, verdict=None, scored_at=None),  # invalid
        _row(id=2),  # valid
    ]
    out = tmp_path / "partial.parquet"
    rows_to_parquet(rows, out)

    report = check_parquet(out)
    assert report.valid == 1
    assert report.invalid == 1
    assert report.errors[0].row_id == 1
    assert "all set or all null" in report.errors[0].reason


def test_check_flags_empty_title(tmp_path: Path) -> None:
    rows = [_row(id=1, title="")]
    out = tmp_path / "empty.parquet"
    rows_to_parquet(rows, out)

    report = check_parquet(out)
    assert report.invalid == 1
    assert "title" in report.errors[0].reason


def test_check_flags_future_posted_date(tmp_path: Path) -> None:
    future = date.today() + timedelta(days=365)
    rows = [_row(id=1, posted_date=future)]
    out = tmp_path / "future.parquet"
    rows_to_parquet(rows, out)

    report = check_parquet(out)
    assert report.invalid == 1
    assert "future" in report.errors[0].reason


def test_check_flags_out_of_range_score(tmp_path: Path) -> None:
    # We can't store 999 via rows_to_parquet because pyarrow uses int32 and
    # 999 fits — the schema does NOT enforce range, only pydantic does.
    rows = [
        _row(
            id=1,
            fit_score=120,
            verdict="fit",
            scored_at=UTC_TS,
        )
    ]
    out = tmp_path / "oor.parquet"
    rows_to_parquet(rows, out)

    report = check_parquet(out)
    assert report.invalid == 1
    assert "fit_score" in report.errors[0].reason


def test_check_empty_parquet(tmp_path: Path) -> None:
    out = tmp_path / "empty.parquet"
    rows_to_parquet([], out)
    report = check_parquet(out)
    assert report == QualityReport(parquet_path=out, total=0, valid=0, invalid=0)
    assert report.all_valid is True


def test_render_report_all_valid_short_circuits(tmp_path: Path) -> None:
    out = tmp_path / "ok.parquet"
    rows_to_parquet([_row(id=1)], out)
    text = render_report(check_parquet(out))
    assert "valid: 1" in text
    assert "invalid: 0" in text
    assert "All rows valid" in text


def test_render_report_lists_errors(tmp_path: Path) -> None:
    rows = [
        _row(id=1),
        _row(id=2, title=""),
        _row(id=3, source="linkedin"),
    ]
    out = tmp_path / "mixed.parquet"
    rows_to_parquet(rows, out)
    text = render_report(check_parquet(out))
    assert "invalid: 2" in text
    assert "id=2" in text
    assert "id=3" in text


def test_render_report_truncates_when_many_errors(tmp_path: Path) -> None:
    rows = [_row(id=i, title="") for i in range(1, 26)]
    out = tmp_path / "many.parquet"
    rows_to_parquet(rows, out)
    text = render_report(check_parquet(out), max_errors=5)
    assert "...and 20 more" in text


def test_row_error_dataclass_equality() -> None:
    err = RowError(row_index=0, row_id=42, reason="bad")
    assert err == RowError(row_index=0, row_id=42, reason="bad")
    assert err != RowError(row_index=1, row_id=42, reason="bad")
