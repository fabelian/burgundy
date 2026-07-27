"""The tracked-manager registry.

``config.MANAGERS`` is the source of truth for *which* managers to follow; this
module keeps the ``managers`` table in step with it.

A CIK is an identity, not a detail — the wrong ten digits would fill the
dashboard with another firm's portfolio and nothing downstream would look
wrong — so each one is taken from that filer's own EDGAR documents. A manager
declared without a CIK is simply not collected from EDGAR.
"""
from __future__ import annotations

from typing import Optional

import config


def sync_from_config(conn) -> int:
    """Upsert ``config.MANAGERS`` into the table. Returns rows written."""
    written = 0
    for m in config.MANAGERS:
        res = conn.execute(
            """
            INSERT INTO managers (slug, name, legal_name, cik, crd,
                                  website_aum_url, website_team_url,
                                  dart_terms, is_active, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (slug) DO UPDATE SET
                name             = EXCLUDED.name,
                legal_name       = EXCLUDED.legal_name,
                crd              = COALESCE(EXCLUDED.crd, managers.crd),
                website_aum_url  = COALESCE(EXCLUDED.website_aum_url, managers.website_aum_url),
                website_team_url = COALESCE(EXCLUDED.website_team_url, managers.website_team_url),
                dart_terms       = EXCLUDED.dart_terms,
                -- Not COALESCEd: retiring a manager has to take effect, and a
                -- flag that only ever turns on could not do it. This is the one
                -- switch that both stops outbound collection (pipeline.run
                -- iterates active()) and removes the manager from the dashboard
                -- (every tab resolves through it), so config must own it.
                is_active        = EXCLUDED.is_active,
                sort_order       = EXCLUDED.sort_order,
                -- config is authoritative: a CIK corrected there must take
                -- effect, or a manager pointed at the wrong filer could never
                -- be fixed. A manager with no CIK in config keeps what it has.
                cik              = COALESCE(EXCLUDED.cik, managers.cik)
            RETURNING id
            """,
            (m["slug"], m["name"], m.get("legal_name"), m.get("cik"),
             m.get("crd"), m.get("website_aum_url"), m.get("website_team_url"),
             m.get("dart_terms") or [], m.get("is_active", True),
             m.get("sort_order", 100)),
        ).fetchone()
        if res:
            written += 1
    return written


def active(conn) -> list[dict]:
    return conn.execute(
        "SELECT * FROM managers WHERE is_active ORDER BY sort_order, name"
    ).fetchall()


def by_slug(conn, slug: str) -> Optional[dict]:
    return conn.execute(
        "SELECT * FROM managers WHERE slug = %s", (slug,)
    ).fetchone()


def default(conn) -> Optional[dict]:
    rows = active(conn)
    return rows[0] if rows else None
