"""Capa de acceso a Postgres usando asyncpg.

Mantiene una pool a nivel de módulo. Las queries usan parámetros posicionales
($1, $2, ...) para evitar inyección. Todos los timestamps van en UTC.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, AsyncIterator, cast

import asyncpg

from .config import Config

log = logging.getLogger(__name__)


@asynccontextmanager
async def connection(config: Config) -> AsyncIterator[asyncpg.Connection]:
    """Abre una conexión de un solo uso. Para scripts cortos (cron) está bien."""
    conn = await asyncpg.connect(config.database_url, ssl="require")
    try:
        yield conn
    finally:
        await conn.close()


async def upsert_jobs(
    conn: asyncpg.Connection, jobs: list[dict[str, Any]]
) -> tuple[int, int]:
    """Inserta jobs nuevos. Para los que ya existen (mismo url) no hace nada.

    Returns (inserted, skipped).
    """
    inserted = 0
    skipped = 0

    for job in jobs:
        posted = _parse_date(job.get("posted_date"))
        result = await conn.execute(
            """
            INSERT INTO jobs (source, url, title, company, location, posted_date, raw_description)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (url) DO NOTHING
            """,
            job["source"],
            job["url"],
            job["title"],
            job.get("company"),
            job.get("location"),
            posted,
            job.get("raw_description"),
        )
        # asyncpg.execute devuelve "INSERT 0 1" si insertó, "INSERT 0 0" si no.
        if result.endswith(" 1"):
            inserted += 1
        else:
            skipped += 1

    return inserted, skipped


async def fetch_unscored(
    conn: asyncpg.Connection, *, limit: int = 50
) -> list[asyncpg.Record]:
    """Devuelve jobs aún no calificados, más recientes primero."""
    rows = await conn.fetch(
        """
        SELECT id, source, url, title, company, location, posted_date, raw_description
        FROM jobs
        WHERE fit_score IS NULL
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return cast(list[asyncpg.Record], rows)


async def save_score(
    conn: asyncpg.Connection,
    *,
    job_id: int,
    fit_score: int,
    verdict: str,
    reason: str,
) -> None:
    await conn.execute(
        """
        UPDATE jobs
        SET fit_score = $1,
            verdict = $2,
            reason = $3,
            scored_at = NOW()
        WHERE id = $4
        """,
        fit_score,
        verdict,
        reason,
        job_id,
    )


async def fetch_undigested_fits(
    conn: asyncpg.Connection, *, min_score: int, limit: int
) -> list[asyncpg.Record]:
    """Jobs marcados 'fit' con score >= min y aún no notificados."""
    rows = await conn.fetch(
        """
        SELECT id, source, url, title, company, location, posted_date,
               fit_score, reason
        FROM jobs
        WHERE verdict = 'fit'
          AND notified_at IS NULL
          AND fit_score >= $1
        ORDER BY fit_score DESC, scored_at DESC
        LIMIT $2
        """,
        min_score,
        limit,
    )
    return cast(list[asyncpg.Record], rows)


async def mark_notified(conn: asyncpg.Connection, ids: list[int]) -> None:
    if not ids:
        return
    await conn.execute(
        "UPDATE jobs SET notified_at = NOW() WHERE id = ANY($1::bigint[])",
        ids,
    )


async def stats(conn: asyncpg.Connection) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE fit_score IS NOT NULL) AS scored,
            COUNT(*) FILTER (WHERE verdict = 'fit') AS fit_count,
            COUNT(*) FILTER (WHERE verdict = 'stretch') AS stretch_count,
            COUNT(*) FILTER (WHERE verdict = 'skip') AS skip_count,
            COUNT(*) FILTER (WHERE notified_at IS NOT NULL) AS notified
        FROM jobs
        """
    )
    return dict(row) if row else {}


def _parse_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value if not isinstance(value, datetime) else value.date()
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        log.warning("db: no se pudo parsear posted_date=%r, se descarta", value)
        return None
