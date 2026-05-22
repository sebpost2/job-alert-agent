"""CLI dispatcher.

Uso:
    python -m job_alert scrape       # solo scrape
    python -m job_alert score        # solo score
    python -m job_alert digest       # solo digest (Telegram + Notion sync)
    python -m job_alert pipeline     # scrape + score
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

# Usar el trust store del sistema (Windows incluye CAs corporativas/AV, Linux usa certifi-equivalente).
# Debe importarse antes que cualquier librería que abra TLS.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

from . import logging_setup

log = logging.getLogger("job_alert")


async def cmd_scrape() -> int:
    import httpx

    from . import config as config_mod
    from . import db
    from .sources import getonboard, remoteok

    cfg = config_mod.load()
    async with httpx.AsyncClient() as client:
        getonboard_jobs = await getonboard.fetch(client, max_per_category=20)
        remoteok_jobs = await remoteok.fetch(client, max_jobs=50)

    all_jobs = getonboard_jobs + remoteok_jobs
    log.info("scrape: %d jobs totales recolectados", len(all_jobs))

    async with db.connection(cfg) as conn:
        inserted, skipped = await db.upsert_jobs(conn, all_jobs)
        stats = await db.stats(conn)
    log.info(
        "scrape: %d nuevos · %d ya existían. DB total=%d, sin scorear=%d",
        inserted,
        skipped,
        stats.get("total", 0),
        stats.get("total", 0) - stats.get("scored", 0),
    )
    return 0


async def cmd_score() -> int:
    from . import config as config_mod
    from . import db
    from . import scorer

    cfg = config_mod.load()

    # Fase 1: leer jobs sin scorear y cerrar la conexión.
    async with db.connection(cfg) as conn:
        rows = await db.fetch_unscored(conn, limit=200)
    if not rows:
        log.info("score: no hay jobs sin scorear")
        return 0
    log.info("score: %d jobs por calificar", len(rows))
    jobs = [dict(r) for r in rows]

    # Fase 2: scorear (puede tardar minutos — no aguantamos conexión Postgres abierta).
    results = await scorer.score_batch(cfg, jobs)

    # Fase 3: guardar todos los resultados con una nueva conexión.
    ok = err = 0
    verdict_counts: dict[str, int] = {}
    async with db.connection(cfg) as conn:
        for job_id, result in results:
            if isinstance(result, Exception):
                err += 1
                continue
            await db.save_score(
                conn,
                job_id=job_id,
                fit_score=result.fit_score,
                verdict=result.verdict,
                reason=result.reason,
            )
            verdict_counts[result.verdict] = verdict_counts.get(result.verdict, 0) + 1
            ok += 1

    log.info("score: ok=%d err=%d · %s", ok, err, verdict_counts)
    return 0


async def cmd_digest() -> int:
    from . import config as config_mod
    from . import db
    from . import notion_sync
    from . import telegram_digest

    cfg = config_mod.load()
    async with db.connection(cfg) as conn:
        # 1. Sincronizar a Notion solo los relevantes (fit + stretch). Los skip
        #    se quedan en Postgres por si se quiere auditar; saturarían la DB.
        relevant = await conn.fetch(
            """
            SELECT id, source, url, title, company, location, posted_date,
                   fit_score, verdict, reason
            FROM jobs
            WHERE verdict IN ('fit', 'stretch')
            ORDER BY scored_at DESC
            LIMIT 200
            """
        )
        jobs_for_notion = [dict(r) for r in relevant]
        log.info("digest: sincronizando %d jobs (fit+stretch) a Notion", len(jobs_for_notion))
        created, updated, errors = await notion_sync.sync(cfg, jobs_for_notion)
        log.info(
            "digest: notion -> creados=%d actualizados=%d errores=%d",
            created,
            updated,
            errors,
        )

        # 2. Sacar top N fits no notificados y mandar a Telegram.
        rows = await db.fetch_undigested_fits(
            conn, min_score=cfg.min_fit_score, limit=cfg.digest_top_n
        )
        jobs_for_telegram = [dict(r) for r in rows]
        log.info("digest: %d fits para Telegram", len(jobs_for_telegram))

        if jobs_for_telegram:
            sent = await telegram_digest.send_digest(cfg, jobs_for_telegram)
            if sent:
                await db.mark_notified(conn, [j["id"] for j in jobs_for_telegram])
        else:
            # Mandar mensaje "sin nuevos fits" igual, para que el usuario sepa que el cron corrió
            await telegram_digest.send_digest(cfg, [])
    return 0


async def cmd_pipeline() -> int:
    log.info("pipeline: scrape + score")
    rc = await cmd_scrape()
    if rc != 0:
        return rc
    return await cmd_score()


COMMANDS = {
    "scrape": cmd_scrape,
    "score": cmd_score,
    "digest": cmd_digest,
    "pipeline": cmd_pipeline,
}


def main() -> int:
    logging_setup.configure()
    parser = argparse.ArgumentParser(prog="job_alert")
    parser.add_argument("command", choices=list(COMMANDS.keys()))
    args = parser.parse_args()
    return asyncio.run(COMMANDS[args.command]())


if __name__ == "__main__":
    sys.exit(main())
