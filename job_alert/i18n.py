"""Capa de i18n: strings EN/ES de cara al usuario y prompts del LLM.

Un único `TypedDict` (`Strings`) fija el contrato: mypy `--strict` obliga a que
`EN` y `ES` tengan exactamente las mismas claves (falta o sobra una → error de
tipado), replicando el patrón de diccionarios tipados con paridad de claves que
uso en mis repos de Next.js.

Selección vía `MESSAGES[lang]`, donde `lang` sale de `JOB_ALERT_LANG`
(default `"en"`).
"""

from __future__ import annotations

from typing import Literal, TypedDict

Lang = Literal["en", "es"]


class Strings(TypedDict):
    # config.py
    missing_env: str  # template: {name}
    # telegram_digest.py
    no_fits: str
    top_fits: str  # template: {n}
    via: str
    view_offer: str
    sources: str
    # scorer.py
    json_shape_hint: str
    system_prompt: str  # template: {cv_summary}, {keywords}, {json_shape_hint}
    user_msg: str  # template: {source}, {title}, {company}, {location}, {desc}
    unknown_company: str
    unspecified_location: str
    no_description: str


def normalize_lang(raw: str) -> Lang:
    """Normaliza el valor crudo de env a un `Lang`. Cualquier cosa que no sea
    `"es"` cae a `"en"` (default)."""
    return "es" if raw.strip().lower() == "es" else "en"


ES: Strings = {
    "missing_env": (
        "Variable de entorno requerida no encontrada: {name}. "
        "Configúrala en .env (local) o en repo Settings → Secrets (GitHub Actions)."
    ),
    "no_fits": "🤖 <b>Job Alert</b>\n\nNo hay nuevos fits hoy. ✅",
    "top_fits": "🤖 <b>Job Alert</b> — top {n} fit(s):\n",
    "via": "vía",
    "view_offer": "Ver oferta",
    "sources": (
        "\n<i>Fuentes: getonboard + remoteok. "
        "Powered by Groq llama-3.1-8b-instant.</i>"
    ),
    "json_shape_hint": """\
Tu respuesta DEBE ser JSON con exactamente este shape:
{{
  "fit_score": <int 0-100>,
  "verdict": "<fit | stretch | skip>",
  "reason": "<1-2 sentences in English, concrete, max 280 chars>"
}}
Sin texto extra, sin markdown, solo el objeto JSON.""",
    "system_prompt": """\
Eres un evaluador estricto de ofertas laborales para este candidato.

{cv_summary}

Keywords del candidato (boost si aparecen): {keywords}

REGLAS DE CLASIFICACIÓN (estrictas):
- "fit": el candidato puede aplicar HOY con probabilidad razonable de pasar filtro inicial.
  Requiere: seniority junior o semi-senior, stack que ya maneja (Python / Odoo / Laravel / Vue / SQL / Docker / Git),
  geo abierta (Perú, LatAm o remoto global), idioma compatible (ES o EN intermedio).
- "stretch": cumple casi todo pero le falta UNA pieza puntual (ej. 1 framework concreto, +1 año de experiencia,
  inglés un poco más alto). Vale la pena postular igual.
- "skip": cualquiera de estos descartes automáticos (bloqueador ABSOLUTO,
  ignora todo lo demás del job aunque el stack matchee perfecto):
    * seniority senior+/staff/principal/director/lead con 5+ años requeridos
    * REQUIERE EXPLÍCITAMENTE 5+ años de experiencia (cualquier fraseo: "5+ years",
      "minimum 5 years", "at least 5 years", "5 años de experiencia mínimo",
      "7+ years", etc.). El candidato tiene <2 años. NO confundir con "5+ years
      preferred" o "nice to have" — solo descarta si es requisito duro.
    * REQUIERE FLUIDEZ en un idioma específico DISTINTO de español o inglés
      (ej. árabe / Arabic, mandarín / Mandarin / Chinese, alemán / German,
      francés / French, portugués / Portuguese, japonés / Japanese,
      italiano / Italian, etc.). Aunque la descripción esté en inglés y el
      stack sea perfect fit, si pide otro idioma como requisito es skip.
    * dominio no-IT (medicina, ventas, marketing, legal, RRHH, diseño gráfico, edición de contenidos)
    * stack completamente ajeno (Salesforce admin, Java enterprise sin Python, SAP, .NET legacy, Cobol)
    * geo bloqueada (solo US citizens, solo on-site en otro país, requiere visa propia)
    * roles de management puro sin componente técnico

Razón SIEMPRE concreta: cita el match o el descarte específico, no escribas frases genéricas.

{json_shape_hint}""",
    "user_msg": """\
Evalúa este job:

Fuente: {source}
Título: {title}
Empresa: {company}
Ubicación: {location}

Descripción:
{desc}""",
    "unknown_company": "(desconocida)",
    "unspecified_location": "(no especificada)",
    "no_description": "(sin descripción)",
}


EN: Strings = {
    "missing_env": (
        "Required environment variable not found: {name}. "
        "Set it in .env (local) or in repo Settings → Secrets (GitHub Actions)."
    ),
    "no_fits": "🤖 <b>Job Alert</b>\n\nNo new fits today. ✅",
    "top_fits": "🤖 <b>Job Alert</b> — top {n} fit(s):\n",
    "via": "via",
    "view_offer": "View job",
    "sources": (
        "\n<i>Sources: getonboard + remoteok. "
        "Powered by Groq llama-3.1-8b-instant.</i>"
    ),
    "json_shape_hint": """\
Your response MUST be JSON with exactly this shape:
{{
  "fit_score": <int 0-100>,
  "verdict": "<fit | stretch | skip>",
  "reason": "<1-2 sentences in English, concrete, max 280 chars>"
}}
No extra text, no markdown, just the JSON object.""",
    "system_prompt": """\
You are a strict evaluator of job postings for this candidate.

{cv_summary}

Candidate keywords (boost if they appear): {keywords}

CLASSIFICATION RULES (strict):
- "fit": the candidate can apply TODAY with a reasonable chance of passing the initial screen.
  Requires: junior or semi-senior seniority, a stack he already handles (Python / Odoo / Laravel / Vue / SQL / Docker / Git),
  open geo (Peru, LatAm or global remote), compatible language (ES or intermediate EN).
- "stretch": meets almost everything but is missing ONE specific piece (e.g. 1 concrete framework, +1 year of experience,
  slightly higher English). Still worth applying.
- "skip": any of these automatic rejections (ABSOLUTE blocker,
  ignore everything else about the job even if the stack matches perfectly):
    * senior+/staff/principal/director/lead seniority with 5+ years required
    * EXPLICITLY REQUIRES 5+ years of experience (any phrasing: "5+ years",
      "minimum 5 years", "at least 5 years", "5 años de experiencia mínimo",
      "7+ years", etc.). The candidate has <2 years. Do NOT confuse this with "5+ years
      preferred" or "nice to have" — only reject if it is a hard requirement.
    * REQUIRES FLUENCY in a specific language OTHER THAN Spanish or English
      (e.g. árabe / Arabic, mandarín / Mandarin / Chinese, alemán / German,
      francés / French, portugués / Portuguese, japonés / Japanese,
      italiano / Italian, etc.). Even if the description is in English and the
      stack is a perfect fit, if it requires another language it is skip.
    * non-IT domain (medicine, sales, marketing, legal, HR, graphic design, content editing)
    * a completely unrelated stack (Salesforce admin, Java enterprise without Python, SAP, .NET legacy, Cobol)
    * blocked geo (US citizens only, on-site only in another country, own visa required)
    * pure management roles with no technical component

ALWAYS give a concrete reason: cite the specific match or rejection, do not write generic phrases.

{json_shape_hint}""",
    "user_msg": """\
Evaluate this job:

Source: {source}
Title: {title}
Company: {company}
Location: {location}

Description:
{desc}""",
    "unknown_company": "(unknown)",
    "unspecified_location": "(not specified)",
    "no_description": "(no description)",
}


MESSAGES: dict[Lang, Strings] = {"es": ES, "en": EN}
