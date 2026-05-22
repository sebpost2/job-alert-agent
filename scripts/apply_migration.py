"""Aplica una migración SQL a la DATABASE_URL del .env (o argumento)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv


async def main(path: Path, database_url: str) -> None:
    sql = path.read_text(encoding="utf-8")
    print(f"Aplicando: {path.name} ({len(sql)} chars)")
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(sql)
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name"
        )
        print("Tablas presentes en la DB:")
        for r in rows:
            print(f"  - {r['table_name']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    load_dotenv()
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL no encontrada — define .env o exporta la variable.")
    migration = Path(sys.argv[1] if len(sys.argv) > 1 else "migrations/001_init.sql")
    asyncio.run(main(migration, db_url))
