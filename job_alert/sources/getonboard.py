"""Cliente para la API JSON pública de getonboard (getonbrd.com)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any

import httpx

log = logging.getLogger(__name__)

BASE = "https://www.getonbrd.com/api/v0"

# Categorías relevantes para el perfil del usuario (dev full-stack + IA).
CATEGORIES: tuple[str, ...] = (
    "programming",
    "machine-learning-ai",
    "data-science-analytics",
    "sysadmin-devops-qa",
)


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return unescape(text).strip()


def _normalize(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        attrs = item["attributes"]
        company_data = (attrs.get("company") or {}).get("data") or {}
        company_name = (company_data.get("attributes") or {}).get("name")

        sections = (attrs.get(k) for k in ("description", "functions", "desirable", "benefits"))
        description = "\n\n".join(t for t in (_strip_html(s) for s in sections) if t)

        countries = attrs.get("countries") or []
        location: str | None
        if attrs.get("remote"):
            location = (
                "Remote"
                if not countries or countries == ["Remote"]
                else f"Remote ({', '.join(countries)})"
            )
        else:
            location = ", ".join(countries) if countries else None

        published_at = attrs.get("published_at")
        posted_date = (
            datetime.fromtimestamp(published_at, tz=timezone.utc).date().isoformat()
            if published_at
            else None
        )

        url = item.get("links", {}).get("public_url")
        title = (attrs.get("title") or "").strip()
        if not url or not title:
            return None

        return {
            "source": "getonboard",
            "url": url,
            "title": title,
            "company": company_name,
            "location": location,
            "posted_date": posted_date,
            "raw_description": description,
        }
    except (KeyError, TypeError) as e:
        log.warning("getonboard: saltando job mal formado (%s)", e)
        return None


async def fetch(
    client: httpx.AsyncClient,
    *,
    max_per_category: int = 20,
) -> list[dict[str, Any]]:
    """Trae jobs de las categorías relevantes. Returns lista de dicts normalizados."""

    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()

    for category in CATEGORIES:
        page = 1
        in_category = 0
        log.info("getonboard: fetching category=%s", category)

        while in_category < max_per_category:
            try:
                r = await client.get(
                    f"{BASE}/categories/{category}/jobs",
                    params={
                        "page": page,
                        "per_page": min(30, max_per_category - in_category),
                        "expand[]": "company",
                    },
                    timeout=20,
                    follow_redirects=True,
                )
                r.raise_for_status()
            except httpx.HTTPError as e:
                log.error("getonboard: error en category=%s page=%d: %s", category, page, e)
                break

            data = r.json()
            items = data.get("data", [])
            if not items:
                break

            for item in items:
                if in_category >= max_per_category:
                    break
                normalized = _normalize(item)
                if not normalized:
                    continue
                if normalized["url"] in seen:
                    continue
                seen.add(normalized["url"])
                jobs.append(normalized)
                in_category += 1

            total_pages = (data.get("meta") or {}).get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1

    log.info("getonboard: %d jobs únicos recolectados", len(jobs))
    return jobs
