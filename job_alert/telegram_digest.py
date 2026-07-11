"""Envío del digest diario a Telegram (parse_mode HTML — menos escape pain)."""

from __future__ import annotations

import html
import logging
from typing import Any

import httpx

from .config import Config
from .i18n import MESSAGES, Lang

log = logging.getLogger(__name__)


def _esc(text: str) -> str:
    """Escapa caracteres HTML especiales en texto plano (no en URLs)."""
    return html.escape(text or "", quote=False)


def _format_message(jobs: list[dict[str, Any]], lang: Lang = "en") -> str:
    s = MESSAGES[lang]
    if not jobs:
        return s["no_fits"]

    lines = [s["top_fits"].format(n=len(jobs))]
    for i, job in enumerate(jobs, start=1):
        title = _esc(job["title"][:100])
        company = _esc(job.get("company") or "?")
        location = _esc(job.get("location") or "?")
        reason = _esc(job.get("reason") or "")
        score = job["fit_score"]
        source = _esc(job["source"])
        # No escapamos URLs — Telegram HTML las acepta crudas dentro de href
        url = job["url"]
        lines.append(
            f"<b>{i}. {title}</b>\n"
            f"  · {company} · {location}\n"
            f'  · fit <code>{score}/100</code> · {s["via"]} {source}\n'
            f"  · <i>{reason}</i>\n"
            f'  · <a href="{url}">{s["view_offer"]}</a>'
        )
    lines.append(s["sources"])
    return "\n\n".join(lines)


async def send_digest(config: Config, jobs: list[dict[str, Any]]) -> bool:
    text = _format_message(jobs, config.lang)
    url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            url,
            json={
                "chat_id": config.telegram_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )

    if r.status_code == 200:
        log.info("telegram: digest enviado (%d jobs)", len(jobs))
        return True

    log.error("telegram: error %d → %s", r.status_code, r.text)
    return False
