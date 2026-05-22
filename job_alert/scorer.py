"""Califica jobs contra el CV usando Groq con structured output."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from groq import AsyncGroq

from .config import Config
from .cv_summary import CV_SUMMARY

log = logging.getLogger(__name__)

MODEL = "llama-3.1-8b-instant"
MAX_DESC_CHARS = 1500

RESPONSE_FORMAT = {"type": "json_object"}

JSON_SHAPE_HINT = """\
Tu respuesta DEBE ser JSON con exactamente este shape:
{
  "fit_score": <int 0-100>,
  "verdict": "<fit | stretch | skip>",
  "reason": "<1-2 frases en español, concretas, máx 280 chars>"
}
Sin texto extra, sin markdown, solo el objeto JSON."""


def _system_prompt(keywords: tuple[str, ...]) -> str:
    return f"""Eres un evaluador estricto de ofertas laborales para este candidato.

{CV_SUMMARY}

Keywords del candidato (boost si aparecen): {", ".join(keywords)}

REGLAS:
- Sé estricto. La mayoría son "skip" (geo-bloqueados, senior puro, stack ajeno).
- "fit" solo para los que realmente puede aplicar HOY.
- Considera: seniority, idioma, geo (Perú/LatAm/remoto), stack.
- Razón CONCRETA, no genérica.

{JSON_SHAPE_HINT}"""


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

    response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _system_prompt(keywords)},
            {"role": "user", "content": user_msg},
        ],
        response_format=RESPONSE_FORMAT,
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
    jobs: list[dict],
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

    try:
        for i, job in enumerate(jobs):
            if i > 0:
                await asyncio.sleep(min_interval_sec)
            try:
                result = await score_job(
                    client,
                    keywords=config.keywords,
                    title=job["title"],
                    company=job.get("company"),
                    location=job.get("location"),
                    source=job["source"],
                    description=job.get("raw_description"),
                )
                out.append((job["id"], result))
                log.info(
                    "scorer: %d/%d → %s(%d) %s",
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
