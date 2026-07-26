"""The tracked-fund registry.

``config.FUNDS`` says which of the managers' own funds are worth reading; this
module keeps the ``funds`` table in step with it, the same way
``pipeline.managers`` does for ``config.MANAGERS``.

A fund whose manager is not tracked is skipped rather than created, so a typo in
``manager_slug`` cannot quietly invent a manager.
"""
from __future__ import annotations

from typing import Optional

import config


def sync_from_config(conn) -> int:
    """Upsert ``config.FUNDS`` into the table. Returns rows written."""
    written = 0
    for f in config.FUNDS:
        manager = conn.execute(
            "SELECT id FROM managers WHERE slug = %s", (f["manager_slug"],)
        ).fetchone()
        if manager is None:
            print(f"[funds] no manager '{f['manager_slug']}' for fund "
                  f"'{f['slug']}'; skipped")
            continue
        res = conn.execute(
            """
            INSERT INTO funds (manager_id, slug, name, mandate, series, currency,
                               doc_url_template, doc_url, cadence, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (manager_id, slug) DO UPDATE SET
                name             = EXCLUDED.name,
                mandate          = EXCLUDED.mandate,
                series           = EXCLUDED.series,
                currency         = EXCLUDED.currency,
                -- config is authoritative for the URL: a template corrected
                -- here must take effect, or a fund pointed at a dead path could
                -- never be fixed. A fund with no template keeps what it has.
                doc_url_template = COALESCE(EXCLUDED.doc_url_template,
                                            funds.doc_url_template),
                doc_url          = COALESCE(EXCLUDED.doc_url, funds.doc_url),
                cadence          = EXCLUDED.cadence,
                sort_order       = EXCLUDED.sort_order
            RETURNING id
            """,
            (manager["id"], f["slug"], f["name"], f["mandate"], f.get("series"),
             f.get("currency", "CAD"), f.get("doc_url_template"),
             f.get("doc_url"), f.get("cadence", "quarterly"),
             f.get("sort_order", 100)),
        ).fetchone()
        if res:
            written += 1
    return written


def for_manager(conn, manager_id: int) -> list[dict]:
    """Active funds of one manager, in display order."""
    return conn.execute(
        "SELECT * FROM funds WHERE manager_id = %s AND is_active"
        " ORDER BY sort_order, name",
        (manager_id,),
    ).fetchall()


def by_slug(conn, manager_id: int, slug: str) -> Optional[dict]:
    return conn.execute(
        "SELECT * FROM funds WHERE manager_id = %s AND slug = %s",
        (manager_id, slug),
    ).fetchone()
