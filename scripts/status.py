"""Quick status check de la DB."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import truststore

truststore.inject_into_ssl()

from job_alert import config as cfg_mod
from job_alert import db


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = cfg_mod.load()
    async with db.connection(cfg) as conn:
        stats = await db.stats(conn)
        print(f"Stats: {stats}")

        fits = await conn.fetch(
            """
            SELECT title, company, location, fit_score, source, reason
            FROM jobs
            WHERE verdict = 'fit'
            ORDER BY fit_score DESC
            LIMIT 10
            """
        )
        print("\nTop fits:")
        for r in fits:
            company = r["company"] or "?"
            print(
                f"  {r['fit_score']:3d} | {r['title'][:50]:50} @ "
                f"{company[:25]:25} [{r['source']}]"
            )
            print(f"        → {r['reason'][:120]}")


if __name__ == "__main__":
    asyncio.run(main())
