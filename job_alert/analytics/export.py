"""Snapshot de la tabla `jobs` a Parquet.

El Parquet resultante es el insumo de los módulos `quality` y `analyze`:
es inmutable, no necesita credenciales para leerlo, y DuckDB lo consulta
en place sin ETL adicional.

El schema arrow se declara explícito (no se infiere desde los datos) para
detectar drifts de tipo y permitir snapshots vacíos sin ambigüedad.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import asyncpg
import pyarrow as pa
import pyarrow.parquet as pq

from .. import db as db_mod
from ..config import Config

log = logging.getLogger(__name__)


JOBS_ARROW_SCHEMA = pa.schema(
    [
        pa.field("id", pa.int64(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("url", pa.string(), nullable=False),
        pa.field("title", pa.string(), nullable=False),
        pa.field("company", pa.string()),
        pa.field("location", pa.string()),
        pa.field("posted_date", pa.date32()),
        pa.field("raw_description", pa.string()),
        pa.field("fit_score", pa.int32()),
        pa.field("verdict", pa.string()),
        pa.field("reason", pa.string()),
        pa.field("scored_at", pa.timestamp("us", tz="UTC")),
        pa.field("notified_at", pa.timestamp("us", tz="UTC")),
        pa.field("created_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

_SELECT_ALL = """
    SELECT id, source, url, title, company, location, posted_date,
           raw_description, fit_score, verdict, reason,
           scored_at, notified_at, created_at
    FROM jobs
    ORDER BY id
"""


def rows_to_parquet(rows: Iterable[dict[str, Any]], path: Path) -> int:
    """Escribe `rows` a `path` siguiendo el schema arrow estricto.

    Devuelve la cantidad de filas escritas. Si `rows` está vacío, escribe
    un Parquet con solo el schema (útil para mantener invariantes downstream).
    """
    rows_list = [_normalize_row(r) for r in rows]
    table = pa.Table.from_pylist(rows_list, schema=JOBS_ARROW_SCHEMA)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return int(table.num_rows)


async def snapshot_to_parquet(
    cfg: Config,
    out_dir: Path,
    *,
    conn: asyncpg.Connection | None = None,
) -> tuple[Path, int]:
    """Lee la tabla completa y la escribe como `jobs_YYYYMMDD.parquet`.

    Si `conn` se provee, se reutiliza (útil para tests); en caso contrario
    se abre una conexión efímera con `db.connection`.
    """
    today = datetime.now(timezone.utc).date().strftime("%Y%m%d")
    path = out_dir / f"jobs_{today}.parquet"

    if conn is not None:
        records = await conn.fetch(_SELECT_ALL)
    else:
        async with db_mod.connection(cfg) as own_conn:
            records = await own_conn.fetch(_SELECT_ALL)

    rows = [dict(r) for r in records]
    count = rows_to_parquet(rows, path)
    log.info("snapshot: %d filas → %s", count, path)
    return path, count


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convierte timestamps naive a UTC para encajar con el schema tz-aware."""
    out = dict(row)
    for key in ("scored_at", "notified_at", "created_at"):
        value = out.get(key)
        if isinstance(value, datetime) and value.tzinfo is None:
            out[key] = value.replace(tzinfo=timezone.utc)
    return out


__all__ = [
    "JOBS_ARROW_SCHEMA",
    "rows_to_parquet",
    "snapshot_to_parquet",
]
