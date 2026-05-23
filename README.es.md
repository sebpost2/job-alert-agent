**[English](README.md) · [Español](README.es.md)**

---

# Job Alert Agent

[![ci](https://github.com/sebpost2/job-alert-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/sebpost2/job-alert-agent/actions/workflows/ci.yml)
[![scrape + score](https://github.com/sebpost2/job-alert-agent/actions/workflows/pipeline.yml/badge.svg)](https://github.com/sebpost2/job-alert-agent/actions/workflows/pipeline.yml)
[![daily digest](https://github.com/sebpost2/job-alert-agent/actions/workflows/digest.yml/badge.svg)](https://github.com/sebpost2/job-alert-agent/actions/workflows/digest.yml)

Agente que cada 12 horas scrapea ofertas laborales de [getonboard](https://www.getonbrd.com) y [RemoteOK](https://remoteok.com), las califica contra mi CV usando un LLM, archiva los relevantes en una database de Notion y manda un digest diario a Telegram con los mejores fits del día.

Construido como pieza de portafolio para demostrar automatización end-to-end con LLMs, deployado completamente gratis vía GitHub Actions cron.

Autor: [sebpost2](https://github.com/sebpost2)

---

## Resultado del agente corriendo

> 📋 **Live dashboard (Notion público)** → **[bevel-rose-8cb.notion.site/Job-Alerts](https://bevel-rose-8cb.notion.site/Job-Alerts-3674d098c1e7807aafe0cf6a3507e526)**
> Cada job que el agente clasificó como `fit` o `stretch` aparece ahí con score, razón, fuente y link a la oferta. Los `skip` se quedan en Postgres por si hay que auditar.
>
> 🔁 **Cómo verificar que funciona**: los badges arriba muestran el estado de los crons en verde. La pestaña [Actions](../../actions) del repo deja el log público de cada ejecución — scrape, score, sync y digest.
>
> 📲 **Telegram**: el digest diario manda el top N fits (default 3) y marca cada uno como notificado para no spamear con repetidos.

<p align="center">
  <img src="docs/telegram-digest.jpg" alt="Telegram digest mostrando top 3 fits del día" width="420">
  <br>
  <em>Digest del bot — top 3 fits con score, fuente, razón y link. Cuando ya envió todo, responde con "No hay nuevos fits hoy".</em>
</p>

## Highlights

- **End-to-end automatizado**: cron de GitHub Actions dispara → Python scrapea 2 fuentes → LLM califica fit → Postgres dedupe → Notion archivo + Telegram digest. Sin intervención humana.
- **LLM con structured output**: cada job se evalúa con Groq (`llama-3.1-8b-instant`), forzando JSON con `fit_score` (0-100), `verdict` (`fit`/`stretch`/`skip`) y `reason`. Razones específicas, no genéricas.
- **Throttle inteligente del rate limit**: respeta los 6000 TPM del free tier de Groq con un intervalo mínimo entre llamadas, manteniendo el sistema en cuota sin caer.
- **CV-aware**: el system prompt incluye un resumen estructurado del candidato (stack, seniority, geo, idioma) — el LLM no califica "es un buen rol" en abstracto, califica "encaja con ESTE candidato".
- **Dos comandos, una arquitectura**: `python -m job_alert scrape` + `score` (cada 12h) y `digest` (diario 8am Lima). Componibles, testeables individualmente.
- **Probado a fondo**: [113 tests unitarios + integración](./tests) con [`pytest`](./pyproject.toml), **96% de cobertura (líneas+ramas)** con gate al 90% en CI, 100% tipado bajo [`mypy --strict`](./pyproject.toml), validado en cada push por [GitHub Actions CI](./.github/workflows/ci.yml). El suite corre en ~3s sin red ni DB.
- **Stack 100% free permanente**: GitHub Actions cron + Neon Postgres + Groq LLM + Notion API + Telegram bot. Cero costo, cero trial.

## Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12+ |
| HTTP | `httpx` (async) |
| Base de datos | PostgreSQL (Neon, serverless) |
| Driver DB | `asyncpg` |
| LLM | Groq llama-3.1-8b-instant |
| LLM SDK | `groq` oficial |
| Notion | API HTTP directa via `httpx` |
| Telegram | Bot API directa via `httpx` |
| Trust store TLS | `truststore` (usa sistema, no certifi) |
| Orquestación | GitHub Actions cron |

## Cómo funciona

```
┌──────────────────────┐     ┌─────────────────────────────────────┐
│ GitHub Actions cron  │────▶│ python -m job_alert scrape          │
│ */12h: scrape+score  │     │   ├─ getonboard (JSON API público)  │
│ daily 8am: digest    │     │   └─ remoteok   (JSON API público)  │
└──────────────────────┘     │           ↓                         │
                             │   upsert por url → Neon Postgres    │
                             └─────────────────────────────────────┘
                                          ↓
                             ┌─────────────────────────────────────┐
                             │ python -m job_alert score           │
                             │   loop unscored jobs:               │
                             │   ├─ regex pre-filtro (no-IT, lead) │
                             │   │   → skip sin gastar call LLM    │
                             │   ├─ Groq llama-3.1-8b-instant      │
                             │   │   (json_object con CV+keywords) │
                             │   ├─ 8s throttle entre calls (TPM)  │
                             │   └─ save fit_score/verdict/reason  │
                             └─────────────────────────────────────┘
                                          ↓
                             ┌─────────────────────────────────────┐
                             │ python -m job_alert digest          │
                             │   ├─ sync fit+stretch → Notion DB   │
                             │   └─ top N fits no notificados →    │
                             │       Telegram bot (HTML parse_mode)│
                             └─────────────────────────────────────┘
```

## Tests y type checking

[![ci](https://github.com/sebpost2/job-alert-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/sebpost2/job-alert-agent/actions/workflows/ci.yml)

Todo el paquete está cubierto por **113 tests de [`pytest`](./tests)** con **96% de cobertura ([líneas+ramas](./pyproject.toml))** — el gate en CI rompe el build si baja del 90% — y type-checked bajo **[`mypy --strict`](./pyproject.toml)**. El [workflow de CI](./.github/workflows/ci.yml) corre los tres en cada push y PR — haz click en el badge para ver el último run (el log imprime `Required test coverage of 90% reached. Total coverage: 96.xx%`).

```bash
pip install -r requirements-dev.txt

python -m mypy        # type checking estricto, cero errores requeridos
python -m pytest      # 113 tests + reporte de coverage, ~4 segundos
```

Layout (cada archivo bajo [`tests/`](./tests) es navegable en GitHub):

```
tests/
├── conftest.py                       # Config fixture compartido
├── test_config.py                    # carga + validación de env vars
├── test_scorer_pure.py               # regex hard-skip + armado del prompt
├── test_scorer_llm.py                # cliente Groq mockeado con AsyncMock
├── test_db.py                        # asyncpg.Connection mockeado, shape de SQL verificado
├── test_notion_sync_pure.py          # builder de propiedades para Notion
├── test_notion_sync_http.py          # flujo completo de sync con HTTP mockeado por respx
├── test_telegram_format.py           # escape HTML + layout del digest
├── test_telegram_digest_http.py      # send_digest con respx
└── sources/
    ├── test_getonboard_normalize.py  # JSON → dict canónico de job
    ├── test_getonboard_http.py       # fetch paginado con respx
    ├── test_remoteok_normalize.py
    └── test_remoteok_http.py
```

Decisiones de diseño:
- **Sin DB real ni red en CI** — `asyncpg.Connection` se reemplaza por `AsyncMock`, HTTP se mockea con `respx`, Groq se mockea parcheando `AsyncGroq`. El suite corre determinístico en ~3 segundos en un runner gratis de GitHub Actions.
- **mypy strict desde el día uno** — `disallow_untyped_decorators`, `no_implicit_reexport`, `warn_return_any` todos activos. Módulos terceros sin tipado (`asyncpg`, `truststore`, `respx`) están allow-listed explícitamente en `pyproject.toml`.
- **Los tests son la spec de los normalizers** — cada campo que el scraper escribe a Postgres está aserto, así que un drift silencioso de schema rompe CI antes de llegar a producción.

## Decisiones de diseño

- **GitHub Actions sobre n8n**: el plan original era n8n cloud (workflow visual), pero discontinuaron el free tier en 2026. GitHub Actions es free permanente y los logs públicos son por sí mismos una pista de que el sistema corre confiablemente — mejor que una captura estática de n8n.
- **Modelo `llama-3.1-8b-instant` sobre `gpt-oss-120b`**: el 120b tiene mejor reasoning pero solo 8000 TPM y soporta `json_schema`; el 8b tiene reasoning suficiente para clasificar fits, `json_object` mode, y similar TPM. Ambos llegan al mismo techo en este caso; el 8b gana en latencia.
- **Pre-filtro regex antes del LLM**: getonboard mezcla roles médicos, ventas, marketing, RR.HH., etc. Una regex barata sobre el título descarta los obvios no-IT y los `staff/principal/director` sin gastar un call a Groq. Reduce ~25-30 % del costo por ciclo.
- **Solo `fit`+`stretch` van a Notion**: los `skip` se quedan en Postgres. La DB de Notion termina con 8-12 filas relevantes por ciclo en vez de 130 — usable como tablero de aplicaciones reales, no como log.
- **Throttle explícito (8s entre calls)**: el SDK de Groq reintenta en 429 pero con concurrencia alta cada retry vuelve a hit TPM. Mejor controlar el ritmo desde el cliente y nunca tocar el límite.
- **Notion API directa (`httpx`) en vez de `notion-client`**: la v3.x del SDK oficial removió `databases.query()` y obliga a migrar a `data_sources.query()` (en flux). Hablar al endpoint HTTP estable es más simple y más estable.
- **Telegram con `parse_mode=HTML`**: `MarkdownV2` exige escapar TODOS los caracteres especiales incluso dentro de URLs. HTML solo necesita escapar `< > &`. Para mensajes con links y razones en español llenas de puntuación, HTML es menos doloroso.
- **CV resumido a ~200 tokens**: el LaTeX completo del CV cuesta ~2000 tokens por call. La versión densa (`cv_summary.py`) baja eso a ~400 sin perder lo que importa para evaluar fit: stack, seniority, geo, preferencias.
- **`truststore` para TLS**: en CI no hace nada; en local Windows con antivirus que intercepta TLS (Avast, Kaspersky), evita el infinito drama de `CERTIFICATE_VERIFY_FAILED`.
- **DB Neon compartida con otros proyectos**: en vez de crear otro Neon project, agregué la tabla `jobs` a la misma instancia que usan mis proyectos de boletas. Dominios distintos, infra compartida — común en producción.

## Correr localmente

### Requisitos

- Python 3.11+
- Una DB Postgres (recomendado: [Neon](https://neon.tech) free tier)
- Cuenta gratis en [Groq](https://console.groq.com)
- Bot de Telegram (vía [@BotFather](https://t.me/BotFather))
- Integración interna de Notion + database creada y conectada

### Setup

```bash
git clone https://github.com/sebpost2/job-alert-agent
cd job-alert-agent

python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # Linux/Mac

pip install -r requirements.txt
```

Copia `.env.example` a `.env` y completa los valores. Luego aplica la migración:

```bash
python scripts/apply_migration.py
```

### Uso

```bash
# Scrape jobs nuevos a la DB
python -m job_alert scrape

# Calificar los pendientes (~8s por job por TPM throttle)
python -m job_alert score

# Sincronizar a Notion + mandar digest a Telegram
python -m job_alert digest

# Atajos
python -m job_alert pipeline   # scrape + score
```

## Variables de entorno

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | Connection string PostgreSQL |
| `GROQ_API_KEY` | API key de Groq |
| `NOTION_TOKEN` | Token de la integración interna |
| `NOTION_DB_ID` | UUID de la database de Notion |
| `TELEGRAM_TOKEN` | Token del bot |
| `TELEGRAM_CHAT_ID` | Tu chat ID (obtenido con `/getUpdates`) |
| `KEYWORDS` | Lista CSV de keywords para guiar al LLM, ej. `python,ia,remoto` |
| `DIGEST_TOP_N` | Cuántos fits incluir en el digest (default `3`) |
| `MIN_FIT_SCORE` | Score mínimo para que un fit aparezca en digest (default `60`) |

En GitHub Actions estos van en `Settings → Secrets and variables → Actions`. `KEYWORDS` puede ir como `Variable` (no es secreto).

## Estructura del proyecto

```
├── .github/workflows/
│   ├── pipeline.yml     # cron 12h: scrape + score
│   └── digest.yml       # cron 8am: digest
├── job_alert/
│   ├── __main__.py      # CLI dispatcher
│   ├── config.py        # validación temprana de env vars
│   ├── db.py            # asyncpg + queries
│   ├── cv_summary.py    # CV comprimido para el prompt
│   ├── scorer.py        # Groq con json_object + throttle
│   ├── notion_sync.py   # upsert via httpx → Notion API
│   ├── telegram_digest.py
│   └── sources/
│       ├── getonboard.py
│       └── remoteok.py
├── migrations/001_init.sql
├── scripts/
│   ├── apply_migration.py
│   └── archive_notion_skips.py  # one-shot housekeeping
└── requirements.txt
```

## Limitaciones conocidas

- **Sin reintentos cross-run**: si `score` falla a mitad de ejecución (por excepción del LLM o de la DB), los jobs no calificados quedarán para el próximo cron. No es ideal pero el cron de 12h cubre rápido.
- **Notion `databases.query` deprecated**: la API de Notion está migrando a `data_sources.query`. La librería oficial `notion-client` aún usa el endpoint viejo y funciona, pero a futuro habrá warnings.
- **RemoteOK manda solo 100 jobs**: si el cron se atrasa varios días podría perder ofertas. Para uso continuo no es problema.
- **Sin filtros geo cliente-side**: la responsabilidad de filtrar US-only/EU-only la tiene el LLM en el scorer. Suficiente en práctica pero el LLM ocasionalmente se equivoca.

---

Construido por [sebpost2](https://github.com/sebpost2) como pieza de portafolio de automatización IA. Fuentes: [getonboard](https://www.getonbrd.com), [RemoteOK](https://remoteok.com) (gracias por su API pública).
