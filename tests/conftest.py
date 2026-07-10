"""Shared fixtures for the job-alert-agent test suite.

Provides a `Config` with deterministic dummy values so modules under test can
build messages, format payloads, and exercise validation without ever reading
the real `.env` or hitting the network.
"""

from __future__ import annotations

import pytest

from job_alert.config import Config


@pytest.fixture
def config() -> Config:
    return Config(
        database_url="postgresql://test:test@localhost:5432/test",
        groq_api_key="test-groq-key",
        notion_token="test-notion-token",
        notion_db_id="00000000-0000-0000-0000-000000000000",
        telegram_token="test-telegram-token",
        telegram_chat_id="12345",
        keywords=("python", "ai", "remote"),
        digest_top_n=3,
        min_fit_score=60,
        lang="es",
    )
