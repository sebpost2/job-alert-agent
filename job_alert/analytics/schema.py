"""Schema pydantic de la tabla `jobs` con invariantes de calidad de datos.

Cada `JobRow` representa una fila válida según las reglas del dominio:
- rangos numéricos (`fit_score` 0-100),
- enumeraciones cerradas (`source`, `verdict`),
- consistencia de scoring (las tres columnas de scoring se setean juntas),
- temporalidad coherente (`notified_at >= scored_at`, `posted_date` no futuro),
- semántica de notificación (solo `fit` se notifica).

El módulo `quality` usa este modelo para validar cada fila de un Parquet
y reportar las filas que violan alguna invariante.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Source = Literal["getonboard", "remoteok"]
Verdict = Literal["fit", "stretch", "skip"]


class JobRow(BaseModel):
    """Una fila de `jobs` con invariantes de calidad."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(gt=0)
    source: Source
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str | None = None
    location: str | None = None
    posted_date: date | None = None
    raw_description: str | None = None
    fit_score: int | None = Field(default=None, ge=0, le=100)
    verdict: Verdict | None = None
    reason: str | None = None
    scored_at: datetime | None = None
    notified_at: datetime | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _scoring_is_atomic(self) -> "JobRow":
        has_score = self.fit_score is not None
        has_verdict = self.verdict is not None
        has_scored_at = self.scored_at is not None
        if not (has_score == has_verdict == has_scored_at):
            raise ValueError(
                "fit_score/verdict/scored_at must be all set or all null "
                f"(got fit_score={self.fit_score!r}, "
                f"verdict={self.verdict!r}, scored_at={self.scored_at!r})"
            )
        return self

    @model_validator(mode="after")
    def _notified_implies_fit(self) -> "JobRow":
        if self.notified_at is None:
            return self
        if self.verdict != "fit":
            raise ValueError(
                f"notified_at is set but verdict={self.verdict!r}, expected 'fit'"
            )
        assert self.scored_at is not None  # _scoring_is_atomic guarantees this
        if self.notified_at < self.scored_at:
            raise ValueError("notified_at must be >= scored_at")
        return self

    @model_validator(mode="after")
    def _posted_not_in_future(self) -> "JobRow":
        if self.posted_date is not None:
            today_utc = datetime.now(timezone.utc).date()
            if self.posted_date > today_utc:
                raise ValueError(
                    f"posted_date {self.posted_date} is in the future"
                )
        return self
