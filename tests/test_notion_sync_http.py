"""Integration tests for notion_sync.sync with mocked HTTP via respx."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import respx

from job_alert import notion_sync
from job_alert.config import Config


def _job(url: str = "https://example.com/job/1") -> dict[str, Any]:
    return {
        "title": "Engineer",
        "company": "Acme",
        "url": url,
        "fit_score": 80,
        "verdict": "fit",
        "reason": "match",
        "source": "getonboard",
        "posted_date": date(2026, 5, 20),
    }


async def test_sync_creates_new_page_when_query_empty(config: Config) -> None:
    async with respx.mock() as mock:
        mock.post(
            f"{notion_sync.NOTION_API}/databases/{config.notion_db_id}/query"
        ).mock(return_value=httpx.Response(200, json={"results": []}))
        create = mock.post(f"{notion_sync.NOTION_API}/pages").mock(
            return_value=httpx.Response(200, json={"id": "new-page"})
        )

        created, updated, errors = await notion_sync.sync(config, [_job()])

    assert (created, updated, errors) == (1, 0, 0)
    assert create.called
    body = create.calls.last.request.read()
    assert b'"database_id"' in body


async def test_sync_updates_existing_page(config: Config) -> None:
    page_id = "existing-page-id"
    async with respx.mock() as mock:
        mock.post(
            f"{notion_sync.NOTION_API}/databases/{config.notion_db_id}/query"
        ).mock(
            return_value=httpx.Response(
                200, json={"results": [{"id": page_id}]}
            )
        )
        update = mock.patch(f"{notion_sync.NOTION_API}/pages/{page_id}").mock(
            return_value=httpx.Response(200, json={"id": page_id})
        )

        created, updated, errors = await notion_sync.sync(config, [_job()])

    assert (created, updated, errors) == (0, 1, 0)
    assert update.called


async def test_sync_counts_errors_and_keeps_processing(config: Config) -> None:
    """A 4xx on one job must not abort the batch."""
    async with respx.mock() as mock:
        # First job → query returns 500.
        mock.post(
            f"{notion_sync.NOTION_API}/databases/{config.notion_db_id}/query"
        ).mock(
            side_effect=[
                httpx.Response(500, json={"error": "boom"}),
                httpx.Response(200, json={"results": []}),
            ]
        )
        mock.post(f"{notion_sync.NOTION_API}/pages").mock(
            return_value=httpx.Response(200, json={"id": "p"})
        )

        created, updated, errors = await notion_sync.sync(
            config,
            [
                _job("https://example.com/a"),
                _job("https://example.com/b"),
            ],
        )

    assert errors == 1
    assert created == 1
    assert updated == 0


async def test_sync_empty_jobs_short_circuits(config: Config) -> None:
    # No HTTP routes registered — if sync calls anything, respx will fail loudly.
    async with respx.mock(assert_all_called=False):
        result = await notion_sync.sync(config, [])
    assert result == (0, 0, 0)


async def test_sync_sends_auth_header(config: Config) -> None:
    async with respx.mock() as mock:
        query = mock.post(
            f"{notion_sync.NOTION_API}/databases/{config.notion_db_id}/query"
        ).mock(return_value=httpx.Response(200, json={"results": []}))
        mock.post(f"{notion_sync.NOTION_API}/pages").mock(
            return_value=httpx.Response(200, json={"id": "p"})
        )

        await notion_sync.sync(config, [_job()])

    assert query.called
    auth = query.calls.last.request.headers["authorization"]
    assert auth == f"Bearer {config.notion_token}"
    assert query.calls.last.request.headers["notion-version"]
