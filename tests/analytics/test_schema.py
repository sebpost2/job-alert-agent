"""Pydantic schema tests: cada invariante en su propio caso valid/invalid."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from job_alert.analytics.schema import JobRow


UTC_TS = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _base_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 1,
        "source": "getonboard",
        "url": "https://example.com/x",
        "title": "Backend Engineer",
        "company": None,
        "location": None,
        "posted_date": None,
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


def test_minimal_unscored_row_is_valid() -> None:
    JobRow.model_validate(_base_row())


def test_scored_fit_row_is_valid() -> None:
    JobRow.model_validate(
        _base_row(
            fit_score=85,
            verdict="fit",
            reason="strong match",
            scored_at=UTC_TS,
        )
    )


def test_notified_fit_row_is_valid() -> None:
    JobRow.model_validate(
        _base_row(
            fit_score=90,
            verdict="fit",
            reason="great",
            scored_at=UTC_TS,
            notified_at=UTC_TS + timedelta(minutes=10),
        )
    )


@pytest.mark.parametrize("bad_id", [0, -1])
def test_id_must_be_positive(bad_id: int) -> None:
    with pytest.raises(ValidationError):
        JobRow.model_validate(_base_row(id=bad_id))


def test_source_must_be_known() -> None:
    with pytest.raises(ValidationError):
        JobRow.model_validate(_base_row(source="linkedin"))


def test_verdict_must_be_known() -> None:
    with pytest.raises(ValidationError):
        JobRow.model_validate(
            _base_row(fit_score=50, verdict="maybe", scored_at=UTC_TS)
        )


def test_empty_title_is_rejected() -> None:
    with pytest.raises(ValidationError):
        JobRow.model_validate(_base_row(title=""))


def test_empty_url_is_rejected() -> None:
    with pytest.raises(ValidationError):
        JobRow.model_validate(_base_row(url=""))


@pytest.mark.parametrize("bad_score", [-1, 101, 999])
def test_fit_score_out_of_range_is_rejected(bad_score: int) -> None:
    with pytest.raises(ValidationError):
        JobRow.model_validate(
            _base_row(fit_score=bad_score, verdict="fit", scored_at=UTC_TS)
        )


def test_partial_scoring_score_only_is_rejected() -> None:
    with pytest.raises(ValidationError, match="all set or all null"):
        JobRow.model_validate(_base_row(fit_score=50))


def test_partial_scoring_verdict_only_is_rejected() -> None:
    with pytest.raises(ValidationError, match="all set or all null"):
        JobRow.model_validate(_base_row(verdict="fit"))


def test_partial_scoring_scored_at_only_is_rejected() -> None:
    with pytest.raises(ValidationError, match="all set or all null"):
        JobRow.model_validate(_base_row(scored_at=UTC_TS))


def test_notified_without_scored_at_is_rejected() -> None:
    # Bypass the scoring-is-atomic check by also setting score+verdict.
    # The notified-implies-fit validator checks scored_at separately.
    row = _base_row(
        fit_score=90,
        verdict="fit",
        scored_at=None,  # this triggers the atomic check first
        notified_at=UTC_TS,
    )
    with pytest.raises(ValidationError):
        JobRow.model_validate(row)


def test_notified_with_stretch_verdict_is_rejected() -> None:
    with pytest.raises(ValidationError, match="expected 'fit'"):
        JobRow.model_validate(
            _base_row(
                fit_score=50,
                verdict="stretch",
                scored_at=UTC_TS,
                notified_at=UTC_TS + timedelta(minutes=1),
            )
        )


def test_notified_before_scored_is_rejected() -> None:
    with pytest.raises(ValidationError, match="notified_at must be >="):
        JobRow.model_validate(
            _base_row(
                fit_score=90,
                verdict="fit",
                scored_at=UTC_TS,
                notified_at=UTC_TS - timedelta(seconds=1),
            )
        )


def test_future_posted_date_is_rejected() -> None:
    future = date.today() + timedelta(days=365)
    with pytest.raises(ValidationError, match="in the future"):
        JobRow.model_validate(_base_row(posted_date=future))


def test_unknown_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        JobRow.model_validate(_base_row(foo="bar"))
