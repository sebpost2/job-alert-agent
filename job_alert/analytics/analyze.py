"""Queries DuckDB sobre snapshots Parquet.

DuckDB lee Parquet en place vía `read_parquet(path)` — no se importa a tabla,
no se persiste estado, cada query es self-contained. La conexión es in-memory
y se descarta al salir.

Las funciones devuelven listas de dicts (no DataFrames ni objetos DuckDB) para
mantener el output trivialmente serializable, fácil de testear y agnóstico
del backend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceFitRate:
    source: str
    total: int
    fit: int
    stretch: int
    skip: int
    unscored: int
    fit_rate_pct: float  # 0.0–100.0


@dataclass(frozen=True)
class ScoreBucket:
    bucket: str  # '80-100' | '60-80' | ... | 'unscored'
    count: int


@dataclass(frozen=True)
class CompanyCount:
    company: str
    postings: int


BUCKET_ORDER: tuple[str, ...] = (
    "80-100",
    "60-80",
    "40-60",
    "20-40",
    "0-20",
    "unscored",
)


def fit_rate_by_source(parquet_path: Path) -> list[SourceFitRate]:
    rows = _query(
        parquet_path,
        """
        SELECT
            source,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE verdict = 'fit') AS fit,
            COUNT(*) FILTER (WHERE verdict = 'stretch') AS stretch,
            COUNT(*) FILTER (WHERE verdict = 'skip') AS skip,
            COUNT(*) FILTER (WHERE verdict IS NULL) AS unscored,
            CASE WHEN COUNT(*) = 0 THEN 0.0
                 ELSE ROUND(100.0 * COUNT(*) FILTER (WHERE verdict = 'fit')
                            / COUNT(*), 2)
            END AS fit_rate_pct
        FROM read_parquet(?)
        GROUP BY source
        ORDER BY total DESC, source
        """,
    )
    return [
        SourceFitRate(
            source=str(r[0]),
            total=int(r[1]),
            fit=int(r[2]),
            stretch=int(r[3]),
            skip=int(r[4]),
            unscored=int(r[5]),
            fit_rate_pct=float(r[6]),
        )
        for r in rows
    ]


def score_distribution(parquet_path: Path) -> list[ScoreBucket]:
    rows = _query(
        parquet_path,
        """
        SELECT
            CASE
                WHEN fit_score IS NULL THEN 'unscored'
                WHEN fit_score < 20 THEN '0-20'
                WHEN fit_score < 40 THEN '20-40'
                WHEN fit_score < 60 THEN '40-60'
                WHEN fit_score < 80 THEN '60-80'
                ELSE '80-100'
            END AS bucket,
            COUNT(*) AS count
        FROM read_parquet(?)
        GROUP BY bucket
        """,
    )
    counts = {str(r[0]): int(r[1]) for r in rows}
    return [ScoreBucket(b, counts.get(b, 0)) for b in BUCKET_ORDER if counts.get(b, 0) > 0]


def top_companies(parquet_path: Path, *, limit: int = 10) -> list[CompanyCount]:
    rows = _query(
        parquet_path,
        """
        SELECT company, COUNT(*) AS postings
        FROM read_parquet(?)
        WHERE company IS NOT NULL AND company <> ''
        GROUP BY company
        ORDER BY postings DESC, company
        LIMIT ?
        """,
        extra_params=(limit,),
    )
    return [CompanyCount(company=str(r[0]), postings=int(r[1])) for r in rows]


def render_report(parquet_path: Path, *, top_n: int = 10) -> str:
    """Compone un reporte de texto a partir de las tres queries principales."""
    total = _count_rows(parquet_path)
    lines: list[str] = [f"# Analytics — {parquet_path.name} ({total} rows)\n"]

    lines.append("## Fit rate by source\n")
    fit_rate = fit_rate_by_source(parquet_path)
    if not fit_rate:
        lines.append("_(no rows)_\n")
    else:
        lines.append("| source     | total | fit | stretch | skip | unscored | fit_rate |")
        lines.append("|------------|------:|----:|--------:|-----:|---------:|---------:|")
        for r in fit_rate:
            lines.append(
                f"| {r.source:<10} | {r.total:>5} | {r.fit:>3} | {r.stretch:>7} | "
                f"{r.skip:>4} | {r.unscored:>8} | {r.fit_rate_pct:>6.2f}% |"
            )
        lines.append("")

    lines.append("## Score distribution\n")
    dist = score_distribution(parquet_path)
    if not dist:
        lines.append("_(no scored rows)_\n")
    else:
        lines.append("| bucket   | count |")
        lines.append("|----------|------:|")
        for b in dist:
            lines.append(f"| {b.bucket:<8} | {b.count:>5} |")
        lines.append("")

    lines.append(f"## Top {top_n} companies\n")
    companies = top_companies(parquet_path, limit=top_n)
    if not companies:
        lines.append("_(no companies)_\n")
    else:
        lines.append("| company | postings |")
        lines.append("|---------|---------:|")
        for c in companies:
            lines.append(f"| {c.company} | {c.postings:>8} |")
        lines.append("")

    return "\n".join(lines)


def _query(
    parquet_path: Path,
    sql: str,
    *,
    extra_params: tuple[Any, ...] = (),
) -> list[tuple[Any, ...]]:
    """Ejecuta `sql` en una conexión efímera, pasando el path como primer parámetro."""
    with duckdb.connect(":memory:") as conn:
        result = conn.execute(sql, (str(parquet_path), *extra_params)).fetchall()
    return result


def _count_rows(parquet_path: Path) -> int:
    rows = _query(parquet_path, "SELECT COUNT(*) FROM read_parquet(?)")
    return int(rows[0][0]) if rows else 0


__all__ = [
    "SourceFitRate",
    "ScoreBucket",
    "CompanyCount",
    "BUCKET_ORDER",
    "fit_rate_by_source",
    "score_distribution",
    "top_companies",
    "render_report",
]
