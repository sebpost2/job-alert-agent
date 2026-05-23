"""Validación de calidad fila por fila sobre un snapshot Parquet.

Carga el Parquet con pyarrow, intenta construir un `JobRow` por fila y
acumula los errores. El reporte resultante es navegable: `valid`,
`invalid`, y una lista de `RowError(id, reason)` para inspección.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from pydantic import ValidationError

from .schema import JobRow

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RowError:
    row_index: int
    row_id: int | None  # None si la fila no tenía id válido
    reason: str


@dataclass(frozen=True)
class QualityReport:
    parquet_path: Path
    total: int
    valid: int
    invalid: int
    errors: list[RowError] = field(default_factory=list)

    @property
    def all_valid(self) -> bool:
        return self.invalid == 0


def check_parquet(parquet_path: Path) -> QualityReport:
    """Valida cada fila del Parquet contra `JobRow`."""
    table = pq.read_table(parquet_path)
    rows: list[dict[str, Any]] = table.to_pylist()

    errors: list[RowError] = []
    valid = 0
    for idx, row in enumerate(rows):
        try:
            JobRow.model_validate(row)
            valid += 1
        except ValidationError as exc:
            errors.append(
                RowError(
                    row_index=idx,
                    row_id=_safe_id(row),
                    reason=_format_error(exc),
                )
            )

    return QualityReport(
        parquet_path=parquet_path,
        total=len(rows),
        valid=valid,
        invalid=len(errors),
        errors=errors,
    )


def render_report(report: QualityReport, *, max_errors: int = 20) -> str:
    """Reporte de texto: header + tabla resumen + primeros N errores."""
    header = (
        f"# Data quality — {report.parquet_path.name}\n\n"
        f"- total: {report.total}\n"
        f"- valid: {report.valid}\n"
        f"- invalid: {report.invalid}\n"
    )
    if report.all_valid:
        return header + "\n_All rows valid._\n"

    lines = [header, "\n## Errors\n"]
    shown = report.errors[:max_errors]
    for err in shown:
        id_str = f"id={err.row_id}" if err.row_id is not None else f"row_index={err.row_index}"
        lines.append(f"- **{id_str}** — {err.reason}")
    if len(report.errors) > max_errors:
        lines.append(f"\n_(...and {len(report.errors) - max_errors} more)_")
    lines.append("")
    return "\n".join(lines)


def _safe_id(row: dict[str, Any]) -> int | None:
    value = row.get("id")
    return int(value) if isinstance(value, int) else None


def _format_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = err.get("msg", "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


__all__ = [
    "RowError",
    "QualityReport",
    "check_parquet",
    "render_report",
]
