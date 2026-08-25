# Retarget job-alert-agent → Odoo técnico / español remoto

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorientar el agente para que surface ofertas remotas de **desarrollo técnico Odoo en español**, y descarte automáticamente los roles funcionales/de implementación que el candidato no quiere.

**Architecture:** El pipeline actual (scrape → score → digest) no cambia de forma. Cambian tres cosas: (1) un hard-skip nuevo en `scorer.py` que descarta títulos funcionales sin gastar un call a Groq, (2) el CV/prompt retargeteado a Odoo técnico + español, (3) una fuente nueva (Remotive) con búsqueda por keyword, porque getonboard/remoteok no traen suficiente Odoo remoto.

**Tech Stack:** Python 3.12+, httpx, respx, pytest (asyncio_mode=auto), mypy --strict, asyncpg, Groq.

**Spec:** Este documento. La sección "Requisitos" abajo es la fuente de verdad — vino de la conversación con el usuario, no de un doc previo.

## Requisitos (del usuario)

1. **Solo Odoo técnico.** "nothing that involves configuring odoo just creating new modules or editing current ones" → descartar consultor funcional, implementador, analista funcional, key user, parametrización.
2. **Preferencia por español.** Priorizar ofertas en español / geo España + LatAm. Inglés del candidato es B1 — no descartar EN, pero bajar prioridad.
3. **Remoto.** Requisito duro que ya existe en el CV_SUMMARY.
4. **Bajo esfuerzo de mantenimiento.** No rediseñar el pipeline. Diff mínimo.

## Global Constraints

- **mypy --strict debe seguir pasando.** Cero `Any` sin `cast`, cero funciones sin anotar.
- **Coverage gate: 90%.** El repo está en ~97%; no bajarlo. Cada módulo nuevo necesita tests.
- **Contrato de `sources/`:** toda `fetch()` devuelve `list[dict[str, Any]]` donde cada dict tiene exactamente estas claves: `source`, `url`, `title`, `company`, `location`, `posted_date`, `raw_description`. `posted_date` es `str` ISO `YYYY-MM-DD` o `None`.
- **Toda `fetch()` nunca lanza por error de red.** Loguea y devuelve `[]` (o continúa al siguiente query). Ver `remoteok.fetch` como referencia.
- **Comentarios y docstrings en español**, convención existente del repo.
- **Commits frecuentes**, uno por tarea.
- Trabajar en `d:\2_MyScripts\FINANCE\job-alert-agent` (NO en el repo `portfolio`).

---

### Task 0: Baseline verde

**Files:** ninguno (solo verificación)

- [ ] **Step 1: Confirmar que la suite pasa antes de tocar nada**

```bash
cd d:/2_MyScripts/FINANCE/job-alert-agent
python -m pytest -q
```

Expected: PASS. Si falla algo, **detente y reporta** — no empieces el plan sobre una base roja.

- [ ] **Step 2: Confirmar mypy limpio**

```bash
python -m mypy --strict job_alert
```

Expected: `Success: no issues found`.

---

### Task 1: Hard-skip de roles Odoo funcionales

Esta es la tarea de mayor valor y no depende de nada externo. Descarta títulos funcionales antes del LLM (ahorra cuota de Groq y saca ruido del digest).

**Files:**
- Modify: `job_alert/scorer.py` (añadir regex + un branch en `_hard_skip_reason`)
- Test: `tests/test_scorer_pure.py` (añadir al final)

**Interfaces:**
- Consumes: nada.
- Produces: `scorer.ODOO_FUNCTIONAL_SKIP: re.Pattern[str]`. `_hard_skip_reason(title: str) -> str | None` mantiene su firma actual.

- [ ] **Step 1: Escribir el test que falla**

Añade al final de `tests/test_scorer_pure.py`:

```python
@pytest.mark.parametrize(
    "title",
    [
        "Consultor Funcional Odoo",
        "Consultora Funcional ERP",
        "Analista Funcional Odoo 17",
        "Functional Consultant - Odoo",
        "Functional Analyst ERP",
        "Implementador Odoo",
        "Implantador de ERP",
        "Implementation Consultant (Odoo)",
        "Soporte Funcional Odoo",
        "Especialista en Parametrización Odoo",
    ],
)
def test_hard_skip_descarta_roles_funcionales(title: str) -> None:
    reason = _hard_skip_reason(title)
    assert reason is not None, f"debería descartarse: {title}"
    assert "funcional" in reason.lower()


@pytest.mark.parametrize(
    "title",
    [
        "Desarrollador Odoo 19",
        "Odoo Developer (Python)",
        "Programador Odoo Python/XML",
        "Backend Developer - Odoo modules",
        "Desarrollador Python ERP",
    ],
)
def test_hard_skip_conserva_roles_tecnicos(title: str) -> None:
    assert _hard_skip_reason(title) is None, f"NO debería descartarse: {title}"
```

Verifica que el import de `_hard_skip_reason` ya exista al inicio del archivo; si no, añádelo:

```python
from job_alert.scorer import _hard_skip_reason
```

- [ ] **Step 2: Correr el test para verificar que falla**

```bash
python -m pytest tests/test_scorer_pure.py -k funcional -v
```

Expected: FAIL — los títulos funcionales devuelven `None` porque el patrón todavía no existe.

- [ ] **Step 3: Implementar el patrón**

En `job_alert/scorer.py`, justo después del bloque `HARD_SKIP_SENIORITY` (línea ~50), añade:

```python
# El candidato hace SOLO desarrollo técnico de Odoo (módulos nuevos, edición de
# módulos existentes). No quiere configuración/implementación funcional, así que
# esos títulos se descartan sin gastar un call a Groq.
ODOO_FUNCTIONAL_SKIP = re.compile(
    r"("
    r"consultor\w*\s+funcional|consultor[ií]a\s+funcional|"
    r"analista\s+funcional|"
    r"functional\s+consultant|functional\s+analyst|"
    r"implementador\w*|implantador\w*|implantaci[óo]n|"
    r"implementation\s+consultant|"
    r"key\s+user|usuario\s+clave|"
    r"soporte\s+funcional|parametrizaci[óo]n"
    r")",
    re.IGNORECASE,
)
```

Nota: sin `\b` al inicio/fin porque varias alternativas terminan en caracteres acentuados (`ó`) donde `\b` se comporta de forma inconsistente. El patrón ya es suficientemente específico para no dar falsos positivos.

Luego, dentro de `_hard_skip_reason`, añade el branch **antes** del `return None` final:

```python
def _hard_skip_reason(title: str) -> str | None:
    """Devuelve el motivo si el job debe saltarse sin pasar por el LLM."""
    m = HARD_SKIP_TITLE_PATTERNS.search(title)
    if m:
        return f"Out of domain (non-IT): '{m.group(1).lower()}'"
    m = HARD_SKIP_SENIORITY.search(title)
    if m:
        return f"Seniority out of junior/semi-senior range: '{m.group(1).lower()}'"
    m = ODOO_FUNCTIONAL_SKIP.search(title)
    if m:
        return f"Rol funcional, no técnico: '{m.group(1).lower()}'"
    return None
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

```bash
python -m pytest tests/test_scorer_pure.py -v
```

Expected: PASS, incluyendo los tests que ya existían.

- [ ] **Step 5: Commit**

```bash
git add job_alert/scorer.py tests/test_scorer_pure.py
git commit -m "feat(scorer): descartar roles Odoo funcionales antes del LLM"
```

---

### Task 2: Retargetear CV_SUMMARY a Odoo técnico + español

**Files:**
- Modify: `job_alert/cv_summary.py` (bloque "Preferencias firmes")
- Test: `tests/test_scorer_pure.py` (añadir un test de contenido)

**Interfaces:**
- Consumes: nada.
- Produces: `CV_SUMMARY: str` sigue siendo un `str` plano inyectado en `_system_prompt`. No cambia la firma.

- [ ] **Step 1: Escribir el test que falla**

Añade a `tests/test_scorer_pure.py`:

```python
def test_cv_summary_declara_preferencia_odoo_tecnico() -> None:
    from job_alert.cv_summary import CV_SUMMARY

    low = CV_SUMMARY.lower()
    assert "técnico" in low
    assert "funcional" in low, "debe decir explícitamente que rechaza rol funcional"
    assert "español" in low
```

- [ ] **Step 2: Correr para verificar que falla**

```bash
python -m pytest tests/test_scorer_pure.py -k cv_summary -v
```

Expected: FAIL — el CV_SUMMARY actual no menciona "funcional" ni la preferencia de idioma.

- [ ] **Step 3: Reescribir el bloque de preferencias**

En `job_alert/cv_summary.py`, reemplaza el bloque `Preferencias firmes:` completo (las 4 líneas que empiezan en `- Remoto preferido.`) por:

```
Preferencias firmes:
- Remoto preferido. Híbrido OK solo en Arequipa. Presencial fuera = no.
- Seniority: Junior o Semi-Senior. Senior puro = no.
- Odoo: SOLO rol técnico (desarrollo de módulos nuevos, edición de módulos existentes,
  Python/XML/QWeb, integraciones, migración de módulos entre versiones).
  Rol funcional = NO (consultor funcional, implementador, parametrización, key user,
  levantamiento de requerimientos, capacitación de usuarios). Esto es bloqueante.
- Idioma: prefiere ofertas en español (España, LatAm, Perú). Inglés B1 — acepta
  ofertas en inglés si el rol no exige fluidez, pero baja prioridad.
- Stack moderno preferido (Python, Odoo, full-stack JS, IA). Stack legacy (COBOL, ABAP) = no.
```

- [ ] **Step 4: Correr los tests**

```bash
python -m pytest tests/test_scorer_pure.py -v && python -m mypy --strict job_alert
```

Expected: PASS + mypy limpio.

- [ ] **Step 5: Commit**

```bash
git add job_alert/cv_summary.py tests/test_scorer_pure.py
git commit -m "feat(cv): retargetear preferencias a Odoo técnico y español"
```

---

### Task 3: Spike — verificar qué devuelve la API de Remotive

No escribas el cliente a ciegas. Confirma la forma real de la respuesta y guarda un fixture.

**Files:**
- Create: `tests/fixtures/remotive_odoo.json`

- [ ] **Step 1: Pedir la respuesta real y guardarla**

```bash
mkdir -p tests/fixtures
python - <<'PY'
import httpx, json
r = httpx.get(
    "https://remotive.com/api/remote-jobs",
    params={"search": "odoo", "limit": 5},
    timeout=30,
    follow_redirects=True,
)
r.raise_for_status()
data = r.json()
with open("tests/fixtures/remotive_odoo.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("top-level keys:", list(data.keys()))
print("job-count:", data.get("job-count"))
PY
```

- [ ] **Step 2: Inspeccionar la forma de un job**

```bash
python - <<'PY'
import json
d = json.load(open("tests/fixtures/remotive_odoo.json", encoding="utf-8"))
jobs = d.get("jobs") or []
print("jobs:", len(jobs))
if jobs:
    print("campos:", sorted(jobs[0].keys()))
    print(json.dumps(jobs[0], ensure_ascii=False)[:900])
else:
    print("SIN JOBS para 'odoo'")
PY
```

**Confirma que existen estos campos en cada job** — el Task 4 los asume:
`url`, `title`, `company_name`, `candidate_required_location`, `publication_date`, `description`, `category`.

**Regla de decisión:**
- Si los campos coinciden → continúa a Task 4 tal cual está escrito.
- Si algún nombre difiere → **ajusta los nombres en `_normalize` de Task 4** para que coincidan con el fixture real, y ajusta los `_sample_item`/`_entry` de los tests igual. No inventes campos.
- Si `jobs` está vacío para "odoo" → sigue igual con Task 4: `QUERIES` incluye también `"python developer"` y `"erp"`, así que la fuente aporta valor de todos modos. Anota el hallazgo en el mensaje de commit.

- [ ] **Step 3: Commit del fixture**

```bash
git add tests/fixtures/remotive_odoo.json
git commit -m "test: fixture real de la API de Remotive para busqueda odoo"
```

---

### Task 4: Fuente nueva — Remotive

**Files:**
- Create: `job_alert/sources/remotive.py`
- Test: `tests/sources/test_remotive_normalize.py`
- Test: `tests/sources/test_remotive_http.py`

**Interfaces:**
- Consumes: `job_alert.sources.strip_html`.
- Produces:
  - `remotive.ENDPOINT: str`
  - `remotive.QUERIES: tuple[str, ...]`
  - `remotive._normalize(item: dict[str, Any]) -> dict[str, Any] | None`
  - `remotive.fetch(client: httpx.AsyncClient, *, max_per_query: int = 25) -> list[dict[str, Any]]`

- [ ] **Step 1: Escribir los tests del normalizador (fallan)**

Crea `tests/sources/test_remotive_normalize.py`:

```python
"""Tests del normalizador de remotive."""

from __future__ import annotations

from typing import Any

from job_alert.sources.remotive import _normalize


def _sample_item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 123,
        "url": "https://remotive.com/remote-jobs/software-dev/odoo-dev-123",
        "title": "  Odoo Developer  ",
        "company_name": "Acme SL",
        "category": "Software Development",
        "candidate_required_location": "  ",
        "publication_date": "2026-05-20T12:00:00",
        "description": "<p>Construir m&oacute;dulos</p>",
    }
    base.update(overrides)
    return base


def test_normalize_happy_path() -> None:
    result = _normalize(_sample_item())
    assert result is not None
    assert result["source"] == "remotive"
    assert result["url"] == "https://remotive.com/remote-jobs/software-dev/odoo-dev-123"
    assert result["title"] == "Odoo Developer"
    assert result["company"] == "Acme SL"
    assert result["location"] == "Worldwide remote", "location vacía debe caer al default"
    assert result["posted_date"] == "2026-05-20"
    desc = result["raw_description"]
    assert isinstance(desc, str)
    assert desc.startswith("Categoría: Software Development")
    assert "Construir módulos" in desc


def test_normalize_conserva_location_explicita() -> None:
    result = _normalize(_sample_item(candidate_required_location="Spain, LATAM"))
    assert result is not None
    assert result["location"] == "Spain, LATAM"


def test_normalize_sin_categoria_omite_prefijo() -> None:
    result = _normalize(_sample_item(category=None))
    assert result is not None
    desc = result["raw_description"]
    assert isinstance(desc, str)
    assert "Categoría:" not in desc
    assert desc == "Construir módulos"


def test_normalize_fecha_ausente_da_none() -> None:
    result = _normalize(_sample_item(publication_date=None))
    assert result is not None
    assert result["posted_date"] is None


def test_normalize_descarta_sin_url() -> None:
    item = _sample_item()
    item.pop("url")
    assert _normalize(item) is None


def test_normalize_descarta_sin_titulo() -> None:
    assert _normalize(_sample_item(title="")) is None
```

- [ ] **Step 2: Correr para verificar que fallan**

```bash
python -m pytest tests/sources/test_remotive_normalize.py -v
```

Expected: FAIL con `ModuleNotFoundError: No module named 'job_alert.sources.remotive'`.

- [ ] **Step 3: Implementar el módulo**

Crea `job_alert/sources/remotive.py`:

```python
"""Cliente para la API JSON pública de remotive.com.

Remotive expone búsqueda por keyword, que es lo que getonboard/remoteok no dan:
nos deja pedir explícitamente ofertas de Odoo en vez de filtrar a posteriori.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from . import strip_html as _strip_html

log = logging.getLogger(__name__)

ENDPOINT = "https://remotive.com/api/remote-jobs"
USER_AGENT = "job-alert-agent (https://github.com/sebpost2/job-alert-agent)"

# Búsquedas dirigidas al perfil: Odoo técnico primero, luego el fallback amplio
# para que la fuente siga aportando aunque un día no haya ofertas de Odoo.
QUERIES: tuple[str, ...] = ("odoo", "python developer", "erp")


def _normalize(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        url = item.get("url")
        title = (item.get("title") or "").strip()
        if not url or not title:
            return None

        company = item.get("company_name")
        location = (item.get("candidate_required_location") or "").strip()
        if not location:
            location = "Worldwide remote"

        # publication_date llega como "2026-05-20T12:00:00"; nos basta la fecha.
        pub = item.get("publication_date")
        posted_date = pub[:10] if isinstance(pub, str) and len(pub) >= 10 else None

        description = _strip_html(item.get("description"))
        category = item.get("category")
        if category:
            description = f"Categoría: {category}\n\n{description}"

        return {
            "source": "remotive",
            "url": url,
            "title": title,
            "company": company,
            "location": location,
            "posted_date": posted_date,
            "raw_description": description,
        }
    except (KeyError, TypeError) as e:
        log.warning("remotive: saltando job mal formado (%s)", e)
        return None


async def fetch(
    client: httpx.AsyncClient, *, max_per_query: int = 25
) -> list[dict[str, Any]]:
    """Trae jobs para cada query de QUERIES, deduplicados por url."""

    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()

    for query in QUERIES:
        log.info("remotive: fetching query=%s", query)
        try:
            r = await client.get(
                ENDPOINT,
                params={"search": query, "limit": max_per_query},
                timeout=20,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.error("remotive: error en query=%s: %s", query, e)
            continue

        entries = r.json().get("jobs") or []
        for item in entries[:max_per_query]:
            normalized = _normalize(item)
            if not normalized:
                continue
            if normalized["url"] in seen:
                continue
            seen.add(normalized["url"])
            jobs.append(normalized)

    log.info("remotive: %d jobs únicos recolectados", len(jobs))
    return jobs
```

- [ ] **Step 4: Correr los tests del normalizador**

```bash
python -m pytest tests/sources/test_remotive_normalize.py -v
```

Expected: PASS.

- [ ] **Step 5: Escribir los tests HTTP**

Crea `tests/sources/test_remotive_http.py`:

```python
"""Tests de integración de remotive.fetch con HTTP mockeado vía respx."""

from __future__ import annotations

from typing import Any

import httpx
import respx

from job_alert.sources import remotive


def _entry(idx: int) -> dict[str, Any]:
    return {
        "id": idx,
        "url": f"https://remotive.com/remote-jobs/x-{idx}",
        "title": f"Odoo Developer {idx}",
        "company_name": "Acme",
        "category": "Software Development",
        "candidate_required_location": "LATAM",
        "publication_date": "2026-05-20T12:00:00",
        "description": "<p>desc</p>",
    }


async def test_fetch_deduplica_entre_queries() -> None:
    async with respx.mock() as mock:
        mock.get(remotive.ENDPOINT).mock(
            return_value=httpx.Response(200, json={"jobs": [_entry(1), _entry(2)]})
        )
        async with httpx.AsyncClient() as client:
            jobs = await remotive.fetch(client, max_per_query=25)

    # Las 3 queries devuelven las mismas urls -> dedup deja 2.
    assert len(jobs) == 2
    assert all(j["source"] == "remotive" for j in jobs)


async def test_fetch_respeta_max_per_query() -> None:
    payload = {"jobs": [_entry(i) for i in range(20)]}
    async with respx.mock() as mock:
        mock.get(remotive.ENDPOINT).mock(return_value=httpx.Response(200, json=payload))
        async with httpx.AsyncClient() as client:
            jobs = await remotive.fetch(client, max_per_query=5)

    assert len(jobs) == 5


async def test_fetch_devuelve_vacio_si_todas_las_queries_fallan() -> None:
    async with respx.mock() as mock:
        mock.get(remotive.ENDPOINT).mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient() as client:
            jobs = await remotive.fetch(client, max_per_query=5)

    assert jobs == []


async def test_fetch_manda_user_agent() -> None:
    async with respx.mock() as mock:
        route = mock.get(remotive.ENDPOINT).mock(
            return_value=httpx.Response(200, json={"jobs": []})
        )
        async with httpx.AsyncClient() as client:
            await remotive.fetch(client, max_per_query=5)

    assert route.called
    assert "job-alert-agent" in route.calls.last.request.headers["user-agent"]
```

- [ ] **Step 6: Correr toda la carpeta de sources + mypy**

```bash
python -m pytest tests/sources/ -v && python -m mypy --strict job_alert
```

Expected: PASS + mypy limpio.

- [ ] **Step 7: Commit**

```bash
git add job_alert/sources/remotive.py tests/sources/test_remotive_normalize.py tests/sources/test_remotive_http.py
git commit -m "feat(sources): anadir Remotive con busqueda por keyword de Odoo"
```

---

### Task 5: Conectar Remotive al pipeline

**Files:**
- Modify: `job_alert/__main__.py:32-57` (`cmd_scrape`)
- Modify: `job_alert/i18n.py` (string `sources` en los bloques `ES` y `EN`)
- Modify: `job_alert/config.py:45` (default de `KEYWORDS`)

**Interfaces:**
- Consumes: `remotive.fetch` de Task 4.
- Produces: nada nuevo.

- [ ] **Step 1: Conectar la fuente en `cmd_scrape`**

En `job_alert/__main__.py`, cambia el import y el bloque de fetch dentro de `cmd_scrape`:

```python
    from .sources import getonboard, remoteok, remotive

    cfg = config_mod.load()
    async with httpx.AsyncClient() as client:
        getonboard_jobs = await getonboard.fetch(client, max_per_category=20)
        remoteok_jobs = await remoteok.fetch(client, max_jobs=50)
        remotive_jobs = await remotive.fetch(client, max_per_query=25)

    all_jobs = getonboard_jobs + remoteok_jobs + remotive_jobs
```

- [ ] **Step 2: Actualizar el crédito de fuentes en el digest**

En `job_alert/i18n.py`, el string `sources` del bloque `ES` dice `"Fuentes: getonboard + remoteok."`. Cámbialo a:

```python
    "sources": (
        "\n<i>Fuentes: getonboard + remoteok + remotive. "
        "Powered by Groq llama-3.1-8b-instant.</i>"
    ),
```

Haz el cambio equivalente en el bloque `EN` (busca el otro `"sources":` en el mismo archivo y añade `+ remotive` igual).

- [ ] **Step 3: Actualizar el default de KEYWORDS**

En `job_alert/config.py` línea 45:

```python
    keywords_raw = _optional("KEYWORDS", "odoo,python,erp,remoto")
```

- [ ] **Step 4: Verificar que nada se rompió**

```bash
python -m pytest -q && python -m mypy --strict job_alert
```

Expected: PASS + mypy limpio. Si `tests/test_i18n.py` afirma el texto exacto de `sources`, actualiza esa aserción también.

- [ ] **Step 5: Commit**

```bash
git add job_alert/__main__.py job_alert/i18n.py job_alert/config.py
git commit -m "feat: conectar Remotive al scrape y retargetear keywords a Odoo"
```

---

### Task 6: Verificación final y configuración de entorno

**Files:**
- Modify: `README.md` y `README.es.md` (mencionar la fuente nueva)

- [ ] **Step 1: Suite completa con coverage**

```bash
python -m pytest --cov=job_alert --cov-report=term-missing -q
```

Expected: PASS con coverage ≥ 90%. Si `remotive.py` baja el número, añade el test que falte antes de seguir.

- [ ] **Step 2: mypy estricto**

```bash
python -m mypy --strict job_alert
```

Expected: `Success: no issues found`.

- [ ] **Step 3: Smoke test real contra la API (sin DB)**

```bash
python - <<'PY'
import asyncio, httpx
from job_alert.sources import remotive

async def main():
    async with httpx.AsyncClient() as c:
        jobs = await remotive.fetch(c, max_per_query=10)
    print(f"{len(jobs)} jobs")
    for j in jobs[:5]:
        print(" -", j["title"], "|", j["location"], "|", j["posted_date"])

asyncio.run(main())
PY
```

Expected: imprime jobs reales. Si imprime `0 jobs`, revisa el fixture de Task 3 — los nombres de campo cambiaron.

- [ ] **Step 4: Actualizar READMEs**

En `README.md` y `README.es.md`, busca donde se listan las fuentes (`getonboard`, `remoteok`) y añade `remotive`. Un renglón, no reescribas el doc.

- [ ] **Step 5: Actualizar las variables en GitHub (manual, no es código)**

En el repo de GitHub → Settings → Secrets and variables → Actions → Variables:
- `KEYWORDS` = `odoo,python,erp,remoto,modulos`
- `JOB_ALERT_LANG` = `es` (para que el prompt y el digest salgan en español)

- [ ] **Step 6: Commit final**

```bash
git add README.md README.es.md
git commit -m "docs: documentar Remotive como tercera fuente"
```

---

## Fuera de alcance (a propósito)

- **No** se toca el esquema de la DB ni las migraciones — las fuentes nuevas usan las mismas columnas.
- **No** se añade scraping de LinkedIn: va contra sus ToS. La alternativa es configurar alertas guardadas de LinkedIn a mano.
- **No** se añaden bolsas de España tipo InfoJobs/Tecnoempleo: requieren API key con aprobación. Evaluar solo si Remotive resulta insuficiente después de una semana corriendo.
