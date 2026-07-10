"""Califica jobs contra el CV usando Groq con structured output."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, cast

from groq import AsyncGroq
from groq.types.chat import ChatCompletionMessageParam

from .config import Config
from .cv_summary import CV_SUMMARY
from .i18n import MESSAGES, Lang

log = logging.getLogger(__name__)

MODEL = "llama-3.1-8b-instant"
MAX_DESC_CHARS = 1500

RESPONSE_FORMAT = {"type": "json_object"}

# Patrones que NO son software dev / IA y aparecen en getonboard. Si matchean
# en el título, no gastamos un call a Groq y los marcamos skip directo.
# Stems like `enfermer`, `psic[oó]log`, `abogad`, `contador` should also catch
# their inflected forms ("enfermera", "psicóloga", "abogados", "contadora"),
# so word stems use \w* before the final \b.
HARD_SKIP_TITLE_PATTERNS = re.compile(
    r"\b("
    r"m[eé]dic[oa]\w*|enfermer\w*|doctor\w*|cl[ií]nic\w*|psic[oó]log\w*|"
    r"contador\w*|abogad\w*|legal counsel|"
    r"redactor\w*|editor m[eé]dic\w*|copywriter|"
    r"community manager|social media|growth manager|"
    r"ventas|sales(?!force)|comercial|account executive|"
    r"recursos humanos|hr business|talent acquisition|reclutador\w*|"
    r"dise[ñn]ador\w* gr[áa]fic\w*|graphic designer|"
    r"chef|cocinero|barista"
    r")\b",
    re.IGNORECASE,
)

# Seniority muy alta que requiere experiencia que Sebastián no tiene aún.
HARD_SKIP_SENIORITY = re.compile(
    r"\b(staff engineer|principal engineer|vp of |head of |director of |"
    r"chief [a-z]+ officer|cto|cio)\b",
    re.IGNORECASE,
)


def _hard_skip_reason(title: str) -> str | None:
    """Devuelve el motivo si el job debe saltarse sin pasar por el LLM."""
    m = HARD_SKIP_TITLE_PATTERNS.search(title)
    if m:
        return f"Out of domain (non-IT): '{m.group(1).lower()}'"
    m = HARD_SKIP_SENIORITY.search(title)
    if m:
        return f"Seniority out of junior/semi-senior range: '{m.group(1).lower()}'"
    return None


# Backward-compat alias: the default-language (es) JSON shape hint, kept so
# callers/tests importing this symbol keep working. Source of truth: i18n.py.
JSON_SHAPE_HINT = MESSAGES["es"]["json_shape_hint"].format()


def _system_prompt(keywords: tuple[str, ...], lang: Lang = "es") -> str:
    s = MESSAGES[lang]
    return s["system_prompt"].format(
        cv_summary=CV_SUMMARY,
        keywords=", ".join(keywords),
        json_shape_hint=s["json_shape_hint"].format(),
    )


@dataclass(frozen=True)
class ScoreResult:
    fit_score: int
    verdict: str
    reason: str


async def score_job(
    client: AsyncGroq,
    *,
    keywords: tuple[str, ...],
    title: str,
    company: str | None,
    location: str | None,
    source: str,
    description: str | None,
    lang: Lang = "es",
) -> ScoreResult:
    desc = (description or "").strip()
    if len(desc) > MAX_DESC_CHARS:
        desc = desc[:MAX_DESC_CHARS] + " [...]"

    user_msg = f"""Evalúa este job:

Fuente: {source}
Título: {title}
Empresa: {company or "(desconocida)"}
Ubicación: {location or "(no especificada)"}

Descripción:
{desc or "(sin descripción)"}"""

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": _system_prompt(keywords, lang)},
        {"role": "user", "content": user_msg},
    ]
    response = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        response_format=cast(Any, RESPONSE_FORMAT),
        temperature=0.2,
    )
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)

    return ScoreResult(
        fit_score=int(data["fit_score"]),
        verdict=str(data["verdict"]),
        reason=str(data["reason"]),
    )


async def score_batch(
    config: Config,
    jobs: list[dict[str, Any]],
    *,
    min_interval_sec: float = 8.0,
) -> list[tuple[int, ScoreResult | Exception]]:
    """Califica jobs en serie con pausa entre llamadas para respetar TPM de Groq.

    Free tier es 6000 TPM para llama-3.1-8b-instant; cada call usa ~1000 tokens
    → 1 call cada ~10s nos da ~6 calls/min sostenido sin tocar el límite.

    Returns lista de (job_id, result_o_excepcion) en el orden de entrada.
    """
    client = AsyncGroq(api_key=config.groq_api_key, max_retries=5)
    out: list[tuple[int, ScoreResult | Exception]] = []
    llm_call_index = 0

    try:
        for i, job in enumerate(jobs):
            hard_skip = _hard_skip_reason(job["title"])
            if hard_skip:
                result = ScoreResult(fit_score=0, verdict="skip", reason=hard_skip)
                out.append((job["id"], result))
                log.info(
                    "scorer: %d/%d hard-skip %s :: %s",
                    i + 1,
                    len(jobs),
                    hard_skip,
                    job["title"][:50],
                )
                continue

            if llm_call_index > 0:
                await asyncio.sleep(min_interval_sec)
            llm_call_index += 1
            try:
                result = await score_job(
                    client,
                    keywords=config.keywords,
                    title=job["title"],
                    company=job.get("company"),
                    location=job.get("location"),
                    source=job["source"],
                    description=job.get("raw_description"),
                    lang=config.lang,
                )
                out.append((job["id"], result))
                log.info(
                    "scorer: %d/%d -> %s(%d) %s",
                    i + 1,
                    len(jobs),
                    result.verdict,
                    result.fit_score,
                    job["title"][:50],
                )
            except Exception as e:
                log.exception(
                    "scorer: error en job id=%s url=%s", job.get("id"), job.get("url")
                )
                out.append((job["id"], e))
    finally:
        await client.close()

    return out
