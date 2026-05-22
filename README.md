# Job Alert Agent

Agente que cada 12 horas scrapea ofertas laborales de [getonboard](https://www.getonbrd.com) y [RemoteOK](https://remoteok.com), las califica contra mi CV usando un LLM, archiva todo en una database de Notion y manda un digest diario a Telegram con los mejores fits del día.

Construido como pieza de portafolio para demostrar automatización end-to-end con LLMs, deployado completamente gratis vía GitHub Actions cron.

Autor: [sebpost2](https://github.com/sebpost2)

---

## Resultado del agente corriendo

> 🔁 **Cómo verificar que funciona**: la pestaña [Actions](../../actions) del repo muestra cada ejecución de los crons. Cada run scrapea, califica y postea — todo público.
>
> 📋 **Database Notion**: vista filtrada a verdict=fit ordenada por score (link a agregar después de hacer la vista pública).

## Highlights

- **End-to-end automatizado**: cron de GitHub Actions dispara → Python scrapea 2 fuentes → LLM califica fit → Postgres dedupe → Notion archivo + Telegram digest. Sin intervención humana.
- **LLM con structured output**: cada job se evalúa con Groq (`llama-3.1-8b-instant`), forzando JSON con `fit_score` (0-100), `verdict` (`fit`/`stretch`/`skip`) y `reason`. Razones específicas, no genéricas.
- **Throttle inteligente del rate limit**: respeta los 6000 TPM del free tier de Groq con un intervalo mínimo entre llamadas, manteniendo el sistema en cuota sin caer.
- **CV-aware**: el system prompt incluye un resumen estructurado del candidato (stack, seniority, geo, idioma) — el LLM no califica "es un buen rol" en abstracto, califica "encaja con ESTE candidato".
- **Dos comandos, una arquitectura**: `python -m job_alert scrape` + `score` (cada 12h) y `digest` (diario 8am Lima). Componibles, testeables individualmente.
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
| Notion | `notion-client` oficial |
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
                             │   ├─ Groq llama-3.1-8b-instant      │
                             │   │   (json_object con CV+keywords) │
                             │   ├─ 8s throttle entre calls (TPM)  │
                             │   └─ save fit_score/verdict/reason  │
                             └─────────────────────────────────────┘
                                          ↓
                             ┌─────────────────────────────────────┐
                             │ python -m job_alert digest          │
                             │   ├─ sync scored → Notion DB        │
                             │   └─ top N fits no notificados →    │
                             │       Telegram bot (MarkdownV2)     │
                             └─────────────────────────────────────┘
```

## Decisiones de diseño

- **GitHub Actions sobre n8n**: el plan original era n8n cloud (workflow visual), pero discontinuaron el free tier en 2026. GitHub Actions es free permanente y los logs públicos son por sí mismos una pista de que el sistema corre confiablemente — mejor que una captura estática de n8n.
- **Modelo `llama-3.1-8b-instant` sobre `gpt-oss-120b`**: el 120b tiene mejor reasoning pero solo 8000 TPM y soporta `json_schema`; el 8b tiene reasoning suficiente para clasificar fits, `json_object` mode, y similar TPM. Ambos llegan al mismo techo en este caso; el 8b gana en latencia.
- **Throttle explícito (8s entre calls)**: el SDK de Groq reintenta en 429 pero con concurrencia alta cada retry vuelve a hit TPM. Mejor controlar el ritmo desde el cliente y nunca tocar el límite.
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
│   ├── notion_sync.py   # upsert via notion-client
│   ├── telegram_digest.py
│   └── sources/
│       ├── getonboard.py
│       └── remoteok.py
├── migrations/001_init.sql
├── scripts/apply_migration.py
└── requirements.txt
```

## Limitaciones conocidas

- **Sin reintentos cross-run**: si `score` falla a mitad de ejecución (por excepción del LLM o de la DB), los jobs no calificados quedarán para el próximo cron. No es ideal pero el cron de 12h cubre rápido.
- **Notion `databases.query` deprecated**: la API de Notion está migrando a `data_sources.query`. La librería oficial `notion-client` aún usa el endpoint viejo y funciona, pero a futuro habrá warnings.
- **RemoteOK manda solo 100 jobs**: si el cron se atrasa varios días podría perder ofertas. Para uso continuo no es problema.
- **Sin filtros geo cliente-side**: la responsabilidad de filtrar US-only/EU-only la tiene el LLM en el scorer. Suficiente en práctica pero el LLM ocasionalmente se equivoca.

---

Construido por [sebpost2](https://github.com/sebpost2) como pieza de portafolio de automatización IA. Fuentes: [getonboard](https://www.getonbrd.com), [RemoteOK](https://remoteok.com) (gracias por su API pública).
