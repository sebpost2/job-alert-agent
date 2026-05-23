"""Tests for DuckDB queries over a fixture Parquet."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from job_alert.analytics.analyze import (
    BUCKET_ORDER,
    CompanyCount,
    ScoreBucket,
    SourceFitRate,
    fit_rate_by_source,
    render_report,
    score_distribution,
    top_companies,
)
from job_alert.analytics.export import rows_to_parquet


UTC_TS = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _row(
    *,
    id: int,
    source: str = "getonboard",
    company: str | None = "Acme",
    fit_score: int | None = None,
    verdict: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "source": source,
        "url": f"https://example.com/{id}",
        "title": f"Job {id}",
        "company": company,
        "location": "Lima",
        "posted_date": date(2025, 1, 1),
        "raw_description": None,
        "fit_score": fit_score,
        "verdict": verdict,
        "reason": "r" if verdict else None,
        "scored_at": UTC_TS if verdict else None,
        "notified_at": None,
        "created_at": UTC_TS,
    }


@pytest.fixture
def parquet_with_mixed_data(tmp_path: Path) -> Path:
    rows: list[dict[str, Any]] = [
        _row(id=1, source="getonboard", fit_score=85, verdict="fit"),
        _row(id=2, source="getonboard", fit_score=75, verdict="fit"),
        _row(id=3, source="getonboard", fit_score=50, verdict="stretch"),
        _row(id=4, source="getonboard", fit_score=30, verdict="skip"),
        _row(id=5, source="getonboard"),  # unscored
        _row(id=6, source="remoteok", fit_score=90, verdict="fit"),
        _row(id=7, source="remoteok", fit_score=10, verdict="skip"),
        _row(id=8, source="remoteok", fit_score=15, verdict="skip"),
        _row(id=9, source="remoteok"),  # unscored
        _row(id=10, source="remoteok", company="BigCo"),  # unscored
    ]
    out = tmp_path / "mixed.parquet"
    rows_to_parquet(rows, out)
    return out


@pytest.fixture
def empty_parquet(tmp_path: Path) -> Path:
    out = tmp_path / "empty.parquet"
    rows_to_parquet([], out)
    return out


def test_fit_rate_by_source_groups_correctly(parquet_with_mixed_data: Path) -> None:
    result = fit_rate_by_source(parquet_with_mixed_data)
    by_src = {r.source: r for r in result}

    assert by_src["getonboard"] == SourceFitRate(
        source="getonboard", total=5, fit=2, stretch=1, skip=1, unscored=1, fit_rate_pct=40.0
    )
    assert by_src["remoteok"] == SourceFitRate(
        source="remoteok", total=5, fit=1, stretch=0, skip=2, unscored=2, fit_rate_pct=20.0
    )


def test_fit_rate_by_source_orders_by_total_desc(parquet_with_mixed_data: Path) -> None:
    result = fit_rate_by_source(parquet_with_mixed_data)
    totals = [r.total for r in result]
    assert totals == sorted(totals, reverse=True)


def test_fit_rate_by_source_empty(empty_parquet: Path) -> None:
    assert fit_rate_by_source(empty_parquet) == []


def test_score_distribution_buckets(parquet_with_mixed_data: Path) -> None:
    result = score_distribution(parquet_with_mixed_data)
    by_bucket = {r.bucket: r.count for r in result}

    # fit_score values present: 85, 75, 50, 30, 90, 10, 15
    assert by_bucket.get("80-100") == 2  # 85, 90
    assert by_bucket.get("60-80") == 1   # 75
    assert by_bucket.get("40-60") == 1   # 50
    assert by_bucket.get("20-40") == 1   # 30
    assert by_bucket.get("0-20") == 2    # 10, 15
    assert by_bucket.get("unscored") == 3  # ids 5, 9, 10


def test_score_distribution_preserves_bucket_order(
    parquet_with_mixed_data: Path,
) -> None:
    result = score_distribution(parquet_with_mixed_data)
    buckets = [r.bucket for r in result]
    # Buckets returned must follow BUCKET_ORDER (high → low → unscored).
    indices = [BUCKET_ORDER.index(b) for b in buckets]
    assert indices == sorted(indices)


def test_score_distribution_excludes_zero_count_buckets(tmp_path: Path) -> None:
    out = tmp_path / "narrow.parquet"
    rows_to_parquet(
        [_row(id=1, fit_score=85, verdict="fit"), _row(id=2, fit_score=90, verdict="fit")],
        out,
    )
    result = score_distribution(out)
    assert {r.bucket for r in result} == {"80-100"}


def test_top_companies_orders_by_postings_desc(
    parquet_with_mixed_data: Path,
) -> None:
    result = top_companies(parquet_with_mixed_data, limit=10)
    counts = [r.postings for r in result]
    assert counts == sorted(counts, reverse=True)


def test_top_companies_ignores_null_companies(tmp_path: Path) -> None:
    rows = [_row(id=1, company=None), _row(id=2, company="Acme"), _row(id=3, company="")]
    out = tmp_path / "nulls.parquet"
    rows_to_parquet(rows, out)
    result = top_companies(out)
    assert result == [CompanyCount(company="Acme", postings=1)]


def test_top_companies_respects_limit(parquet_with_mixed_data: Path) -> None:
    result = top_companies(parquet_with_mixed_data, limit=1)
    assert len(result) == 1


def test_top_companies_empty(empty_parquet: Path) -> None:
    assert top_companies(empty_parquet) == []


def test_render_report_contains_section_headers(
    parquet_with_mixed_data: Path,
) -> None:
    report = render_report(parquet_with_mixed_data, top_n=3)
    assert "# Analytics" in report
    assert "## Fit rate by source" in report
    assert "## Score distribution" in report
    assert "## Top 3 companies" in report


def test_render_report_includes_total_row_count(
    parquet_with_mixed_data: Path,
) -> None:
    report = render_report(parquet_with_mixed_data)
    assert "(10 rows)" in report


def test_render_report_handles_empty_parquet(empty_parquet: Path) -> None:
    report = render_report(empty_parquet)
    assert "(0 rows)" in report
    assert "no rows" in report
    assert "no scored rows" in report
    assert "no companies" in report


def test_score_bucket_dataclass_equality() -> None:
    assert ScoreBucket("80-100", 5) == ScoreBucket("80-100", 5)
    assert ScoreBucket("80-100", 5) != ScoreBucket("60-80", 5)
