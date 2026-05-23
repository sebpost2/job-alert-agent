"""One-shot: fetch the raw_description of the 9 jobs that match the target titles.

Match by case-insensitive substring against the `title` column. Prints one
markdown block per job so the assistant can read them back from the file
written to stdout-redirected output.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Make the package importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TARGET_TITLES = [
    "Software engineer",
    "AI Product Engineer",
    "AI Automation Operator",
    "Software Development Engineer",
    "Full-Stack Software Engineer",
    "Forward Deployed Engineer Agentic Platform",
    "Software Engineer Platform",
    "QA Automation Engineer (Python)",
    "Data Platform Engineer (Data Quality & AI Workflows)",
]


async def main() -> None:
    dsn = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(dsn, ssl="require")
    out_path = Path(__file__).resolve().parent / "target_jds_output.md"
    parts: list[str] = []
    try:
        for target in TARGET_TITLES:
            stem = target.split("(")[0].strip()
            rows = await conn.fetch(
                """
                SELECT id, source, url, title, company, location, posted_date,
                       fit_score, verdict, reason, raw_description
                FROM jobs
                WHERE title ILIKE $1
                ORDER BY scored_at DESC NULLS LAST, created_at DESC
                LIMIT 3
                """,
                f"%{stem}%",
            )
            parts.append(f"\n\n========== TARGET: {target} ==========")
            if not rows:
                parts.append("NO MATCH IN DB")
                continue
            for r in rows:
                parts.append(f"\n--- id={r['id']} | {r['source']} | {r['title']}")
                parts.append(f"company:  {r['company']}")
                parts.append(f"location: {r['location']}")
                parts.append(f"posted:   {r['posted_date']}")
                parts.append(
                    f"verdict:  {r['verdict']} ({r['fit_score']})  reason: {r['reason']}"
                )
                parts.append(f"url:      {r['url']}")
                parts.append("description:")
                parts.append((r["raw_description"] or "").strip())
                parts.append("--- end ---")
    finally:
        await conn.close()
    out_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {out_path} ({sum(len(p) for p in parts)} chars)")


if __name__ == "__main__":
    asyncio.run(main())
