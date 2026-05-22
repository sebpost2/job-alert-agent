"""One-shot: archiva (soft-delete) en Notion todas las páginas con verdict=skip.

Útil tras introducir el filtro `fit+stretch only` en cmd_digest — limpia el
ruido histórico sin tocar Postgres. Las páginas archivadas pueden recuperarse
desde el trash de Notion si hace falta.

Uso:
    python -m scripts.archive_notion_skips
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Permitir correrlo desde la raíz del repo: `python scripts/archive_notion_skips.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import httpx

from job_alert.config import load
from job_alert.logging_setup import configure
from job_alert.notion_sync import NOTION_API, NOTION_VERSION

log = logging.getLogger(__name__)


async def main() -> int:
    configure()
    cfg = load()
    headers = {
        "Authorization": f"Bearer {cfg.notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    archived = errors = 0
    page_ids: list[str] = []

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        cursor: str | None = None
        while True:
            body: dict = {
                "filter": {"property": "Verdict", "select": {"equals": "skip"}},
                "page_size": 100,
            }
            if cursor:
                body["start_cursor"] = cursor
            resp = await client.post(
                f"{NOTION_API}/databases/{cfg.notion_db_id}/query", json=body
            )
            resp.raise_for_status()
            data = resp.json()
            page_ids.extend(r["id"] for r in data["results"])
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        log.info("archive: encontradas %d paginas con verdict=skip", len(page_ids))

        for page_id in page_ids:
            try:
                r = await client.patch(
                    f"{NOTION_API}/pages/{page_id}", json={"archived": True}
                )
                r.raise_for_status()
                archived += 1
            except Exception as e:
                errors += 1
                log.warning("archive: error en page %s: %s", page_id, e)

    log.info("archive: completado. archivadas=%d errores=%d", archived, errors)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
