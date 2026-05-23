"""Tests for the Groq-backed paths of the scorer using a mock client.

The hard-skip regex is covered in `test_scorer_pure.py`. Here we make sure:
- the LLM path parses a valid JSON response into a ScoreResult
- score_batch never calls the LLM for titles that hit the cheap pre-filter
- score_batch captures per-job exceptions instead of failing the whole batch
- the inter-call throttle is actually awaited between LLM calls
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from job_alert import scorer
from job_alert.config import Config
from job_alert.scorer import ScoreResult


def _groq_response(payload: dict[str, Any]) -> MagicMock:
    """Build a fake AsyncGroq chat-completion response."""
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock(message=msg)
    response = MagicMock(choices=[choice])
    return response


def _fake_groq_client(*payloads: dict[str, Any]) -> AsyncMock:
    client = AsyncMock()
    # chat.completions.create is an async method that we call with kwargs.
    client.chat.completions.create = AsyncMock(
        side_effect=[_groq_response(p) for p in payloads]
    )
    client.close = AsyncMock()
    return client


async def test_score_job_parses_json_into_result() -> None:
    client = _fake_groq_client(
        {"fit_score": 80, "verdict": "fit", "reason": "stack matches"}
    )
    result = await scorer.score_job(
        client,
        keywords=("python",),
        title="Senior Python Engineer",
        company="Acme",
        location="Remote",
        source="getonboard",
        description="desc",
    )
    assert result == ScoreResult(fit_score=80, verdict="fit", reason="stack matches")
    client.chat.completions.create.assert_awaited_once()


async def test_score_job_truncates_long_description() -> None:
    long = "x" * (scorer.MAX_DESC_CHARS + 500)
    client = _fake_groq_client(
        {"fit_score": 0, "verdict": "skip", "reason": "n/a"}
    )
    await scorer.score_job(
        client,
        keywords=(),
        title="t",
        company=None,
        location=None,
        source="getonboard",
        description=long,
    )
    sent_user = client.chat.completions.create.await_args.kwargs["messages"][1][
        "content"
    ]
    assert "[...]" in sent_user
    # The chunk before [...] is exactly MAX_DESC_CHARS chars.
    assert ("x" * scorer.MAX_DESC_CHARS) in sent_user


async def test_score_batch_skips_llm_for_hard_skip_titles(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job whose title regex-matches a non-IT role must never reach Groq."""
    client = _fake_groq_client()  # no payloads → would raise if called
    monkeypatch.setattr(scorer, "AsyncGroq", lambda **kw: client)

    jobs = [
        {"id": 1, "title": "Médico ocupacional", "source": "getonboard"},
        {"id": 2, "title": "Community Manager", "source": "getonboard"},
    ]
    # No sleep needed: hard-skip path never waits.
    monkeypatch.setattr("job_alert.scorer.asyncio.sleep", AsyncMock())

    results = await scorer.score_batch(config, jobs, min_interval_sec=0)

    assert len(results) == 2
    for _, r in results:
        assert isinstance(r, ScoreResult)
        assert r.verdict == "skip"
        assert r.fit_score == 0
    client.chat.completions.create.assert_not_called()


async def test_score_batch_calls_llm_and_throttles(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _fake_groq_client(
        {"fit_score": 70, "verdict": "fit", "reason": "a"},
        {"fit_score": 50, "verdict": "stretch", "reason": "b"},
    )
    monkeypatch.setattr(scorer, "AsyncGroq", lambda **kw: client)
    sleep_mock = AsyncMock()
    monkeypatch.setattr("job_alert.scorer.asyncio.sleep", sleep_mock)

    jobs = [
        {"id": 10, "title": "Python Engineer", "source": "getonboard"},
        {"id": 11, "title": "Backend Engineer", "source": "remoteok"},
    ]
    results = await scorer.score_batch(config, jobs, min_interval_sec=3.0)

    assert [r.verdict for _, r in results if isinstance(r, ScoreResult)] == [
        "fit",
        "stretch",
    ]
    # One sleep between the two LLM calls; not before the first.
    sleep_mock.assert_awaited_once_with(3.0)
    assert client.chat.completions.create.await_count == 2


async def test_score_batch_captures_individual_failures(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            _groq_response({"fit_score": 90, "verdict": "fit", "reason": "ok"}),
            RuntimeError("Groq exploded"),
        ]
    )
    client.close = AsyncMock()
    monkeypatch.setattr(scorer, "AsyncGroq", lambda **kw: client)
    monkeypatch.setattr("job_alert.scorer.asyncio.sleep", AsyncMock())

    jobs = [
        {"id": 1, "title": "Python Engineer", "source": "getonboard"},
        {"id": 2, "title": "Backend Engineer", "source": "remoteok"},
    ]
    results = await scorer.score_batch(config, jobs, min_interval_sec=0)

    assert len(results) == 2
    assert isinstance(results[0][1], ScoreResult)
    assert isinstance(results[1][1], RuntimeError)
    # And the client was closed even though one call raised.
    client.close.assert_awaited_once()
