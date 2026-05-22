"""Carga variables de entorno con validación temprana.

En GitHub Actions vienen del secrets/vars del repo.
En local vienen de .env (gracias a python-dotenv).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Variable de entorno requerida no encontrada: {name}. "
            f"Configúrala en .env (local) o en repo Settings → Secrets (GitHub Actions)."
        )
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


def load() -> Config:
    keywords_raw = _optional("KEYWORDS", "python,ia,remoto")
    keywords = tuple(k.strip().lower() for k in keywords_raw.split(",") if k.strip())

    return Config(
        database_url=_required("DATABASE_URL"),
        groq_api_key=_required("GROQ_API_KEY"),
        notion_token=_required("NOTION_TOKEN"),
        notion_db_id=_required("NOTION_DB_ID"),
        telegram_token=_required("TELEGRAM_TOKEN"),
        telegram_chat_id=_required("TELEGRAM_CHAT_ID"),
        keywords=keywords,
        digest_top_n=int(_optional("DIGEST_TOP_N", "3")),
        min_fit_score=int(_optional("MIN_FIT_SCORE", "60")),
    )
