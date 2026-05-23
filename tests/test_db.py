"""Tests for the DB layer using an AsyncMock connection.

We never touch a real database here — only verify the SQL strings and the
parameter binding via the asyncpg connection contract (execute / fetch /
fetchrow). Schema correctness is enforced by `migrations/001_init.sql` and
caught at runtime; what we want to lock down here is the *shape* of every
call so refactors don't silently change semantics.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest

from job_alert import db


def _conn() -> AsyncMock:
    """An AsyncMock that behaves like an asyncpg.Connection enough for our tests."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock()
    conn.fetchrow = AsyncMock()
    return conn


async def test_upsert_jobs_counts_inserted_vs_skipped() -> None:
    conn = _conn()
    # asyncpg.execute returns "INSERT 0 N" — 1 means inserted, 0 means conflict.
    conn.execute.side_effect = ["INSERT 0 1", "INSERT 0 0", "INSERT 0 1"]

    jobs: list[dict[str, Any]] = [
        {
            "source": "getonboard",
            "url": f"https://example.com/{i}",
            "title": f"Job {i}",
            "company": "Acme",
            "location": "Remote",
            "posted_date": "2026-05-20",
            "raw_description": "desc",
        }
        for i in range(3)
    ]

    inserted, skipped = await db.upsert_jobs(conn, jobs)

    assert (inserted, skipped) == (2, 1)
    assert conn.execute.await_count == 3
    # First call binds the URL and posted_date positionally.
    args = conn.execute.call_args_list[0].args
    assert args[1] == "getonboard"
    assert args[2] == "https://example.com/0"
    assert args[6] == date(2026, 5, 20)


async def test_upsert_jobs_handles_empty_input() -> None:
    conn = _conn()
    inserted, skipped = await db.upsert_jobs(conn, [])
    assert (inserted, skipped) == (0, 0)
    conn.execute.assert_not_called()


async def test_upsert_jobs_parses_invalid_date_as_none() -> None:
    conn = _conn()
    conn.execute.return_value = "INSERT 0 1"

    jobs: list[dict[str, Any]] = [
        {
            "source": "getonboard",
            "url": "https://example.com/x",
            "title": "Job",
            "posted_date": "not-a-date",
        }
    ]
    await db.upsert_jobs(conn, jobs)
    args = conn.execute.call_args_list[0].args
    assert args[6] is None  # posted_date param


async def test_fetch_unscored_passes_limit() -> None:
    conn = _conn()
    conn.fetch.return_value = []
    rows = await db.fetch_unscored(conn, limit=42)
    assert rows == []
    sql, limit = conn.fetch.call_args.args
    assert "fit_score IS NULL" in sql
    assert limit == 42


async def test_save_score_binds_all_fields() -> None:
    conn = _conn()
    await db.save_score(
        conn, job_id=7, fit_score=88, verdict="fit", reason="match"
    )
    args = conn.execute.call_args.args
    assert "UPDATE jobs" in args[0]
    assert args[1:] == (88, "fit", "match", 7)


async def test_fetch_undigested_fits_filters_by_score_and_limit() -> None:
    conn = _conn()
    conn.fetch.return_value = []
    await db.fetch_undigested_fits(conn, min_score=70, limit=5)
    sql, min_score, limit = conn.fetch.call_args.args
    assert "verdict = 'fit'" in sql
    assert "notified_at IS NULL" in sql
    assert (min_score, limit) == (70, 5)


async def test_mark_notified_noop_for_empty_list() -> None:
    conn = _conn()
    await db.mark_notified(conn, [])
    conn.execute.assert_not_called()


async def test_mark_notified_binds_ids_array() -> None:
    conn = _conn()
    await db.mark_notified(conn, [1, 2, 3])
    args = conn.execute.call_args.args
    assert "notified_at = NOW()" in args[0]
    assert args[1] == [1, 2, 3]


async def test_stats_returns_dict_from_row() -> None:
    conn = _conn()
    # asyncpg.Record-like: behaves like dict, here we just give a plain dict.
    conn.fetchrow.return_value = {
        "total": 100,
        "scored": 80,
        "fit_count": 10,
        "stretch_count": 20,
        "skip_count": 50,
        "notified": 5,
    }
    result = await db.stats(conn)
    assert result["total"] == 100
    assert result["fit_count"] == 10


async def test_stats_returns_empty_when_no_row() -> None:
    conn = _conn()
    conn.fetchrow.return_value = None
    result = await db.stats(conn)
    assert result == {}


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-05-20", date(2026, 5, 20)),
        (date(2026, 5, 20), date(2026, 5, 20)),
        (None, None),
        ("invalid", None),
        ("", None),
    ],
)
def test_parse_date_handles_known_shapes(
    value: str | date | None, expected: date | None
) -> None:
    assert db._parse_date(value) == expected
