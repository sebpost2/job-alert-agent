"""Integration tests for getonboard.fetch with mocked HTTP via respx."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from job_alert.sources import getonboard


def _gob_item(
    idx: int, title: str = "Python Engineer", *, scope: str = "x"
) -> dict[str, Any]:
    return {
        "links": {
            "public_url": f"https://www.getonbrd.com/jobs/{scope}-{idx}"
        },
        "attributes": {
            "title": title,
            "description": "<p>desc</p>",
            "functions": "",
            "desirable": "",
            "benefits": "",
            "remote": True,
            "countries": [],
            "published_at": 1779580800,  # 2026-05-20 UTC
            "company": {"data": {"attributes": {"name": "Acme"}}},
        },
    }


async def test_fetch_iterates_categories_and_dedupes() -> None:
    async with respx.mock(assert_all_called=False) as mock:
        for category in getonboard.CATEGORIES:
            mock.get(
                f"{getonboard.BASE}/categories/{category}/jobs",
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "data": [_gob_item(1), _gob_item(2)],
                        "meta": {"total_pages": 1},
                    },
                )
            )

        async with httpx.AsyncClient() as client:
            jobs = await getonboard.fetch(client, max_per_category=20)

    # Same two items in every category — dedupe by URL should leave exactly 2.
    assert len(jobs) == 2
    assert {j["url"] for j in jobs} == {
        "https://www.getonbrd.com/jobs/x-1",
        "https://www.getonbrd.com/jobs/x-2",
    }
    assert all(j["source"] == "getonboard" for j in jobs)


async def test_fetch_respects_max_per_category() -> None:
    async with respx.mock(assert_all_called=False) as mock:
        for category in getonboard.CATEGORIES:
            mock.get(
                f"{getonboard.BASE}/categories/{category}/jobs",
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "data": [
                            _gob_item(i, f"Role {category}-{i}", scope=category)
                            for i in range(10)
                        ],
                        "meta": {"total_pages": 1},
                    },
                )
            )

        async with httpx.AsyncClient() as client:
            jobs = await getonboard.fetch(client, max_per_category=3)

    # Each category contributes exactly 3 (URLs are unique per category).
    assert len(jobs) == 4 * 3


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_fetch_swallows_http_error_and_moves_on(status: int) -> None:
    async with respx.mock(assert_all_called=False) as mock:
        for category in getonboard.CATEGORIES:
            mock.get(
                f"{getonboard.BASE}/categories/{category}/jobs",
            ).mock(return_value=httpx.Response(status))

        async with httpx.AsyncClient() as client:
            jobs = await getonboard.fetch(client, max_per_category=5)

    # Errors logged, no raises, empty result.
    assert jobs == []


async def test_fetch_paginates_until_total_pages() -> None:
    """When per-category cap is large, the loop must follow `meta.total_pages`."""
    async with respx.mock(assert_all_called=False) as mock:
        for category in getonboard.CATEGORIES:
            route = mock.get(
                f"{getonboard.BASE}/categories/{category}/jobs",
            )
            route.mock(
                side_effect=[
                    httpx.Response(
                        200,
                        json={
                            "data": [_gob_item(1, scope=category)],
                            "meta": {"total_pages": 2},
                        },
                    ),
                    httpx.Response(
                        200,
                        json={
                            "data": [_gob_item(2, scope=category)],
                            "meta": {"total_pages": 2},
                        },
                    ),
                ]
            )

        async with httpx.AsyncClient() as client:
            jobs = await getonboard.fetch(client, max_per_category=2)

    # 4 categories × 2 unique items each = 8.
    assert len(jobs) == 4 * 2
