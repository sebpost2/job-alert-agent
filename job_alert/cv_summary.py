"""Resumen comprimido del CV para inyectar en el prompt del LLM.

Mantenido corto a propósito (token budget). Fuente de verdad: CV/cv_english.tex.
"""

CV_SUMMARY = """\
Candidato: Sebastián Postigo, egresado UCSP (Arequipa, Perú, 2025). Inglés B1.

Experiencia:
- Inbrasol Web Services (Nov 2025-Abr 2026, RxH): Desarrollador Odoo 19 (Python, XML, QWeb), SUNAT/UBL, CPQ.
- Neo Plus Business (Feb-May 2025, practicante): Laravel 11, Vue 3, GitLab CI, JWT, MessagePack.

Stack: Python, TypeScript, Odoo, Laravel, Next.js, Vue 3, FastAPI, PostgreSQL, Prisma, Groq/Vercel AI SDK, Docker, Git.
Portafolio personal (live): invoice-extractor (LLM visión), invoice-chat (agente tool use), job-alert-agent.

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

Reglas de veredicto:
- fit (70-100): junior/semi-senior remoto/LatAm, stack que ya conoce, idioma manejable.
- stretch (40-69): pide 1-2 años más de experiencia, stack adyacente que puede aprender, o inglés más alto.
- skip (0-39): senior 5+ años, stack ajeno, presencial fuera de Arequipa, geo-bloqueado (US-only, EU-only), o no-técnico.
""".strip()
