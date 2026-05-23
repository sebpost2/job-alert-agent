"""Tests for env-var loading and validation."""

from __future__ import annotations

import pytest

from job_alert import config as config_mod


REQUIRED_VARS = (
    "DATABASE_URL",
    "GROQ_API_KEY",
    "NOTION_TOKEN",
    "NOTION_DB_ID",
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID",
)


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED_VARS:
        monkeypatch.setenv(name, f"value-{name.lower()}")
    monkeypatch.delenv("KEYWORDS", raising=False)
    monkeypatch.delenv("DIGEST_TOP_N", raising=False)
    monkeypatch.delenv("MIN_FIT_SCORE", raising=False)


def test_load_uses_defaults_when_optionals_missing(fake_env: None) -> None:
    cfg = config_mod.load()
    assert cfg.database_url == "value-database_url"
    assert cfg.groq_api_key == "value-groq_api_key"
    assert cfg.notion_token == "value-notion_token"
    assert cfg.notion_db_id == "value-notion_db_id"
    assert cfg.telegram_token == "value-telegram_token"
    assert cfg.telegram_chat_id == "value-telegram_chat_id"
    assert cfg.keywords == ("python", "ia", "remoto")
    assert cfg.digest_top_n == 3
    assert cfg.min_fit_score == 60


def test_load_parses_keywords_csv(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    monkeypatch.setenv("KEYWORDS", " Python ,, AI ,remote ")
    cfg = config_mod.load()
    # Empties skipped, whitespace trimmed, lowercased.
    assert cfg.keywords == ("python", "ai", "remote")


def test_load_overrides_numeric_optionals(
    monkeypatch: pytest.MonkeyPatch, fake_env: None
) -> None:
    monkeypatch.setenv("DIGEST_TOP_N", "5")
    monkeypatch.setenv("MIN_FIT_SCORE", "75")
    cfg = config_mod.load()
    assert cfg.digest_top_n == 5
    assert cfg.min_fit_score == 75


@pytest.mark.parametrize("missing", REQUIRED_VARS)
def test_load_raises_on_missing_required(
    monkeypatch: pytest.MonkeyPatch, fake_env: None, missing: str
) -> None:
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        config_mod.load()
