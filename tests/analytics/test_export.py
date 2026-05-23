"""Tests for the Postgres → Parquet exporter."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pyarrow.parquet as pq
import pytest

from job_alert.analytics.export import (
    JOBS_ARROW_SCHEMA,
    rows_to_parquet,
    snapshot_to_parquet,
)
from job_alert.config import Config


UTC_TS = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 1,
        "source": "getonboard",
        "url": "https://example.com/x",
        "title": "Backend",
        "company": "Acme",
        "location": "Lima",
        "posted_date": date(2025, 1, 1),
        "raw_description": "blah",
        "fit_score": None,
        "verdict": None,
        "reason": None,
        "scored_at": None,
        "notified_at": None,
        "created_at": UTC_TS,
    }
    base.update(overrides)
    return base


def test_rows_to_parquet_writes_explicit_schema(tmp_path: Path) -> None:
    out = tmp_path / "jobs.parquet"
    rows_to_parquet([_row()], out)

    table = pq.read_table(out)
    assert table.schema.equals(JOBS_ARROW_SCHEMA)


def test_rows_to_parquet_returns_row_count(tmp_path: Path) -> None:
    out = tmp_path / "jobs.parquet"
    count = rows_to_parquet([_row(id=1), _row(id=2, url="https://example.com/y")], out)
    assert count == 2


def test_rows_to_parquet_empty_writes_schema_only_file(tmp_path: Path) -> None:
    out = tmp_path / "empty.parquet"
    count = rows_to_parquet([], out)
    assert count == 0
    table = pq.read_table(out)
    assert table.num_rows == 0
    assert table.schema.equals(JOBS_ARROW_SCHEMA)


def test_rows_to_parquet_creates_parent_dirs(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "deeper" / "jobs.parquet"
    rows_to_parquet([_row()], out)
    assert out.exists()


def test_rows_to_parquet_preserves_nulls(tmp_path: Path) -> None:
    out = tmp_path / "jobs.parquet"
    rows_to_parquet(
        [_row(company=None, location=None, posted_date=None, raw_description=None)],
        out,
    )
    table = pq.read_table(out)
    assert table.column("company").to_pylist() == [None]
    assert table.column("location").to_pylist() == [None]
    assert table.column("posted_date").to_pylist() == [None]


def test_rows_to_parquet_coerces_naive_timestamps_to_utc(tmp_path: Path) -> None:
    naive = datetime(2025, 1, 1, 12, 0, 0)  # no tzinfo
    out = tmp_path / "jobs.parquet"
    rows_to_parquet([_row(created_at=naive)], out)
    table = pq.read_table(out)
    # round-trips back as tz-aware UTC
    got = table.column("created_at").to_pylist()[0]
    assert got == datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_rows_to_parquet_roundtrip_scored_fit(tmp_path: Path) -> None:
    out = tmp_path / "jobs.parquet"
    rows_to_parquet(
        [
            _row(
                fit_score=85,
                verdict="fit",
                reason="good",
                scored_at=UTC_TS,
                notified_at=UTC_TS,
            )
        ],
        out,
    )
    table = pq.read_table(out)
    assert table.column("fit_score").to_pylist() == [85]
    assert table.column("verdict").to_pylist() == ["fit"]
    assert table.column("scored_at").to_pylist() == [UTC_TS]


async def test_snapshot_to_parquet_uses_provided_conn(
    tmp_path: Path, config: Config
) -> None:
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[_row(id=1), _row(id=2, url="https://example.com/y")])

    path, count = await snapshot_to_parquet(config, tmp_path, conn=conn)

    assert count == 2
    assert path.exists()
    assert path.parent == tmp_path
    assert path.name.startswith("jobs_")
    assert path.suffix == ".parquet"
    # The SQL passed in must select the right columns in the right order.
    sql = conn.fetch.call_args.args[0]
    for col in (
        "id",
        "source",
        "url",
        "title",
        "company",
        "location",
        "posted_date",
        "raw_description",
        "fit_score",
        "verdict",
        "reason",
        "scored_at",
        "notified_at",
        "created_at",
    ):
        assert col in sql


async def test_snapshot_to_parquet_empty_table(
    tmp_path: Path, config: Config
) -> None:
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    path, count = await snapshot_to_parquet(config, tmp_path, conn=conn)
    assert count == 0
    table = pq.read_table(path)
    assert table.num_rows == 0


async def test_snapshot_to_parquet_filename_uses_today_utc(
    tmp_path: Path, config: Config
) -> None:
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    path, _ = await snapshot_to_parquet(config, tmp_path, conn=conn)
    today = datetime.now(timezone.utc).date().strftime("%Y%m%d")
    assert path.name == f"jobs_{today}.parquet"


@pytest.mark.asyncio
async def test_snapshot_to_parquet_opens_own_connection_when_none_given(
    tmp_path: Path, config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When `conn` is None, the exporter must open one via db.connection."""
    from contextlib import asynccontextmanager
    from typing import AsyncIterator

    opened: list[str] = []
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])

    @asynccontextmanager
    async def fake_connection(_cfg: Config) -> AsyncIterator[AsyncMock]:
        opened.append("open")
        try:
            yield conn
        finally:
            opened.append("close")

    monkeypatch.setattr("job_alert.analytics.export.db_mod.connection", fake_connection)

    path, count = await snapshot_to_parquet(config, tmp_path)
    assert opened == ["open", "close"]
    assert count == 0
    assert path.exists()
