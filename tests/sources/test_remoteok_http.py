"""Integration tests for remoteok.fetch with mocked HTTP via respx."""

from __future__ import annotations

from typing import Any

import httpx
import respx

from job_alert.sources import remoteok


def _entry(idx: int) -> dict[str, Any]:
    return {
        "id": str(idx),
        "url": f"https://remoteok.com/remote-jobs/x-{idx}",
        "position": f"Role {idx}",
        "company": "Acme",
        "location": "",
        "epoch": 1779580800,  # 2026-05-20 UTC
        "description": "<p>desc</p>",
        "tags": ["python"],
    }


async def test_fetch_skips_legal_preamble() -> None:
    legal = {"legal": "by using this API you agree..."}
    payload = [legal, _entry(1), _entry(2)]

    async with respx.mock() as mock:
        mock.get(remoteok.ENDPOINT).mock(
            return_value=httpx.Response(200, json=payload)
        )

        async with httpx.AsyncClient() as client:
            jobs = await remoteok.fetch(client, max_jobs=50)

    assert len(jobs) == 2
    assert all(j["source"] == "remoteok" for j in jobs)


async def test_fetch_respects_max_jobs() -> None:
    payload = [{"legal": "..."}] + [_entry(i) for i in range(20)]
    async with respx.mock() as mock:
        mock.get(remoteok.ENDPOINT).mock(
            return_value=httpx.Response(200, json=payload)
        )

        async with httpx.AsyncClient() as client:
            jobs = await remoteok.fetch(client, max_jobs=5)

    assert len(jobs) == 5


async def test_fetch_returns_empty_on_http_error() -> None:
    async with respx.mock() as mock:
        mock.get(remoteok.ENDPOINT).mock(return_value=httpx.Response(503))

        async with httpx.AsyncClient() as client:
            jobs = await remoteok.fetch(client, max_jobs=50)

    assert jobs == []


async def test_fetch_sends_user_agent_header() -> None:
    async with respx.mock() as mock:
        route = mock.get(remoteok.ENDPOINT).mock(
            return_value=httpx.Response(200, json=[{"legal": "..."}])
        )

        async with httpx.AsyncClient() as client:
            await remoteok.fetch(client, max_jobs=5)

    assert route.called
    sent_ua = route.calls.last.request.headers["user-agent"]
    assert "job-alert-agent" in sent_ua
