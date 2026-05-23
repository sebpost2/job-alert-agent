"""Cliente para la API JSON pública de remoteok.com."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any

import httpx

log = logging.getLogger(__name__)

# RemoteOK pide explícitamente en su API TOS que enlacemos a su URL canónica
# y los mencionemos como fuente. Lo cumplimos guardando su `url` tal cual y
# mencionándolos en el README + en el digest de Telegram.
ENDPOINT = "https://remoteok.com/api"
USER_AGENT = "job-alert-agent (https://github.com/sebpost2/job-alert-agent)"


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return unescape(text).strip()


def _normalize(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        url = item.get("url")
        title = (item.get("position") or "").strip()
        if not url or not title:
            return None

        company = item.get("company")
        location = (item.get("location") or "").strip() or "Worldwide remote"

        epoch = item.get("epoch")
        posted_date = (
            datetime.fromtimestamp(epoch, tz=timezone.utc).date().isoformat()
            if epoch
            else None
        )

        description = _strip_html(item.get("description"))
        tags = item.get("tags") or []
        if tags:
            description = f"Tags: {', '.join(tags)}\n\n{description}"

        return {
            "source": "remoteok",
            "url": url,
            "title": title,
            "company": company,
            "location": location,
            "posted_date": posted_date,
            "raw_description": description,
        }
    except (KeyError, TypeError) as e:
        log.warning("remoteok: saltando job mal formado (%s)", e)
        return None


async def fetch(
    client: httpx.AsyncClient, *, max_jobs: int = 50
) -> list[dict[str, Any]]:
    """Trae jobs recientes de RemoteOK. El endpoint devuelve ~100 por request."""

    log.info("remoteok: fetching feed")
    try:
        r = await client.get(
            ENDPOINT,
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.error("remoteok: error en feed: %s", e)
        return []

    entries = r.json()
    # La primera entrada es un "legal" / TOS, no un job — la saltamos.
    jobs_raw = [e for e in entries if isinstance(e, dict) and "id" in e]

    jobs: list[dict[str, Any]] = []
    for item in jobs_raw[:max_jobs]:
        normalized = _normalize(item)
        if normalized:
            jobs.append(normalized)

    log.info("remoteok: %d jobs recolectados", len(jobs))
    return jobs
