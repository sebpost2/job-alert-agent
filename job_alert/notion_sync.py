"""Sincronización a una database Notion vía HTTP directo.

notion-client 3.x removió `databases.query` en favor de `data_sources.query`,
así que hablamos directo al endpoint estable `POST /v1/databases/{id}/query`
y `POST /v1/pages`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Config

log = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _properties_for(job: dict[str, Any]) -> dict[str, Any]:
    title = job["title"] or "(sin título)"
    company = (job.get("company") or "")[:2000]
    reason = (job.get("reason") or "")[:2000]

    posted = job.get("posted_date")
    posted_iso = posted.isoformat() if posted else None

    return {
        "Title": {"title": [{"text": {"content": title[:2000]}}]},
        "Company": {"rich_text": [{"text": {"content": company}}]},
        "URL": {"url": job["url"]},
        "Fit Score": {"number": job.get("fit_score")},
        "Verdict": (
            {"select": {"name": job["verdict"]}}
            if job.get("verdict") in ("fit", "stretch", "skip")
            else {"select": None}
        ),
        "Reason": {"rich_text": [{"text": {"content": reason}}]},
        "Source": (
            {"select": {"name": job["source"]}}
            if job.get("source")
            else {"select": None}
        ),
        "Posted": ({"date": {"start": posted_iso}} if posted_iso else {"date": None}),
    }


async def sync(config: Config, jobs: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Upsert de cada job a la database Notion (buscando por URL).

    Returns (created, updated, errors).
    """
    if not jobs:
        return (0, 0, 0)

    headers = {
        "Authorization": f"Bearer {config.notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    created = updated = errors = 0

    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        for job in jobs:
            try:
                # Buscar página existente con la misma URL
                query_resp = await client.post(
                    f"{NOTION_API}/databases/{config.notion_db_id}/query",
                    json={
                        "filter": {"property": "URL", "url": {"equals": job["url"]}},
                        "page_size": 1,
                    },
                )
                query_resp.raise_for_status()
                results = query_resp.json().get("results", [])

                props = _properties_for(job)

                if results:
                    page_id = results[0]["id"]
                    upd = await client.patch(
                        f"{NOTION_API}/pages/{page_id}",
                        json={"properties": props},
                    )
                    upd.raise_for_status()
                    updated += 1
                else:
                    cr = await client.post(
                        f"{NOTION_API}/pages",
                        json={
                            "parent": {"database_id": config.notion_db_id},
                            "properties": props,
                        },
                    )
                    cr.raise_for_status()
                    created += 1
            except httpx.HTTPStatusError as e:
                errors += 1
                log.warning(
                    "notion: %s en job url=%s body=%s",
                    e.response.status_code,
                    job.get("url"),
                    e.response.text[:200],
                )
            except Exception as e:
                errors += 1
                log.warning("notion: error inesperado en job url=%s: %s", job.get("url"), e)

    return (created, updated, errors)
