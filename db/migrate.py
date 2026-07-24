"""Minimal migration runner (no Alembic).

Applies every ``db/migrations/NNN_*.sql`` file in order once, tracking applied
files in a ``schema_migrations`` table. Safe to run repeatedly on local and
Railway Postgres.

Usage:  python -m db.migrate
"""
from __future__ import annotations

import pathlib
import sys

from db.conn import connect

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


def _ensure_tracking_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename    TEXT PRIMARY KEY,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _applied(conn) -> set[str]:
    rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    return {r["filename"] for r in rows}


def migrate() -> int:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    applied_count = 0
    with connect() as conn:
        _ensure_tracking_table(conn)
        conn.commit()
        done = _applied(conn)
        for f in files:
            if f.name in done:
                print(f"[migrate] skip {f.name} (already applied)")
                continue
            print(f"[migrate] applying {f.name} ...")
            sql = f.read_text(encoding="utf-8")
            conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)", (f.name,)
            )
            conn.commit()
            applied_count += 1
            print(f"[migrate] applied {f.name}")
    print(f"[migrate] done ({applied_count} new migration(s))")
    return applied_count


if __name__ == "__main__":
    try:
        migrate()
    except Exception as exc:  # pragma: no cover - operational surface
        print(f"[migrate] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
