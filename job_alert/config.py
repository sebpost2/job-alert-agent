"""Carga variables de entorno con validación temprana.

En GitHub Actions vienen del secrets/vars del repo.
En local vienen de .env (gracias a python-dotenv).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from .i18n import MESSAGES, Lang, normalize_lang

load_dotenv()


def _required(name: str, lang: Lang) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(MESSAGES[lang]["missing_env"].format(name=name))
    return value


def _optional(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Config:
    database_url: str
    groq_api_key: str
    notion_token: str
    notion_db_id: str
    telegram_token: str
    telegram_chat_id: str
    keywords: tuple[str, ...]
    digest_top_n: int
    min_fit_score: int
    lang: Lang


def load() -> Config:
    keywords_raw = _optional("KEYWORDS", "python,ia,remoto")
    keywords = tuple(k.strip().lower() for k in keywords_raw.split(",") if k.strip())
    lang = normalize_lang(_optional("JOB_ALERT_LANG", "en"))

    return Config(
        database_url=_required("DATABASE_URL", lang),
        groq_api_key=_required("GROQ_API_KEY", lang),
        notion_token=_required("NOTION_TOKEN", lang),
        notion_db_id=_required("NOTION_DB_ID", lang),
        telegram_token=_required("TELEGRAM_TOKEN", lang),
        telegram_chat_id=_required("TELEGRAM_CHAT_ID", lang),
        keywords=keywords,
        digest_top_n=int(_optional("DIGEST_TOP_N", "3")),
        min_fit_score=int(_optional("MIN_FIT_SCORE", "60")),
        lang=lang,
    )
