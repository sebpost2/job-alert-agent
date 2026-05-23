"""Integration tests for telegram_digest.send_digest with mocked HTTP."""

from __future__ import annotations

import json
from typing import Any

import httpx
import respx

from job_alert import telegram_digest
from job_alert.config import Config


async def test_send_digest_posts_correct_payload(config: Config) -> None:
    jobs: list[dict[str, Any]] = [
        {
            "title": "Engineer",
            "company": "Acme",
            "location": "Remote",
            "fit_score": 90,
            "reason": "match",
            "source": "getonboard",
            "url": "https://example.com/x",
        }
    ]
    url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"

    async with respx.mock() as mock:
        route = mock.post(url).mock(return_value=httpx.Response(200, json={"ok": True}))

        ok = await telegram_digest.send_digest(config, jobs)

    assert ok is True
    assert route.called
    payload = json.loads(route.calls.last.request.read())
    assert payload["chat_id"] == config.telegram_chat_id
    assert payload["parse_mode"] == "HTML"
    assert payload["disable_web_page_preview"] is True
    assert "Engineer" in payload["text"]


async def test_send_digest_returns_false_on_error(config: Config) -> None:
    url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"
    async with respx.mock() as mock:
        mock.post(url).mock(return_value=httpx.Response(429, text="rate limited"))

        ok = await telegram_digest.send_digest(config, [])

    assert ok is False


async def test_send_digest_empty_still_sends_heartbeat(config: Config) -> None:
    """The user wants to know the cron actually ran, so we send "no fits" too."""
    url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"
    async with respx.mock() as mock:
        route = mock.post(url).mock(return_value=httpx.Response(200, json={"ok": True}))

        ok = await telegram_digest.send_digest(config, [])

    assert ok is True
    assert route.called
    payload = json.loads(route.calls.last.request.read())
    assert "No hay nuevos fits hoy" in payload["text"]
