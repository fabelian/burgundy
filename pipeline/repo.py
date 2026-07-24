"""Persistence helpers (repository layer).

All snapshot inserts are idempotent via ON CONFLICT DO NOTHING on the
unique keys defined in the schema. Returns the number of rows actually
inserted so collectors can report ``new_rows``.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Iterable, Optional

from collectors.types import (
    AumRow,
    HoldingRow,
    KrHoldingRow,
    PersonnelRow,
    RawDoc,
)


# ---- raw_documents -------------------------------------------------------

def insert_raw(conn, doc: RawDoc) -> Optional[int]:
    """Insert a raw document. Returns its id, or the existing id on conflict.

    None is returned only if the row exists and we could not read it back
    (should not happen). Idempotency key: (source, content_hash).
    """
    row = conn.execute(
        """
        INSERT INTO raw_documents (source, external_id, url, content_hash, payload)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (source, content_hash) DO NOTHING
        RETURNING id
        """,
        (doc.source, doc.external_id, doc.url, doc.content_hash, doc.payload),
    ).fetchone()
    if row:
        return row["id"]
    existing = conn.execute(
        "SELECT id FROM raw_documents WHERE source = %s AND content_hash = %s",
        (doc.source, doc.content_hash),
    ).fetchone()
    return existing["id"] if existing else None


def raw_exists(conn, source: str, content_hash: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM raw_documents WHERE source = %s AND content_hash = %s",
        (source, content_hash),
    ).fetchone()
    return row is not None


def external_id_seen(conn, source: str, external_id: str) -> bool:
    """True if a raw doc with this source/external_id already exists."""
    row = conn.execute(
        "SELECT 1 FROM raw_documents WHERE source = %s AND external_id = %s LIMIT 1",
        (source, external_id),
    ).fetchone()
    return row is not None


# ---- holdings (13F) ------------------------------------------------------

def insert_holdings(conn, rows: Iterable[HoldingRow], raw_id: Optional[int]) -> int:
    n = 0
    for r in rows:
        res = conn.execute(
            """
            INSERT INTO holdings
              (as_of_date, filed_at, accession_no, is_amendment, cusip, ticker,
               name, shares, value_kusd, weight, raw_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (accession_no, cusip) DO NOTHING
            RETURNING id
            """,
            (
                r.as_of_date, r.filed_at, r.accession_no, r.is_amendment, r.cusip,
                r.ticker, r.name, r.shares, r.value_kusd, r.weight, raw_id,
            ),
        ).fetchone()
        if res:
            n += 1
    return n


# ---- kr_holdings (DART) --------------------------------------------------

def insert_kr_holdings(conn, rows: Iterable[KrHoldingRow], raw_id: Optional[int]) -> int:
    n = 0
    for r in rows:
        res = conn.execute(
            """
            INSERT INTO kr_holdings
              (as_of_date, filed_at, rcept_no, corp_code, corp_name, ticker,
               shares, ownership_pct, report_type, raw_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (rcept_no, corp_code) DO NOTHING
            RETURNING id
            """,
            (
                r.as_of_date, r.filed_at, r.rcept_no, r.corp_code, r.corp_name,
                r.ticker, r.shares, r.ownership_pct, r.report_type, raw_id,
            ),
        ).fetchone()
        if res:
            n += 1
    return n


# ---- aum_history ---------------------------------------------------------

def insert_aum(conn, rows: Iterable[AumRow], raw_id: Optional[int]) -> int:
    n = 0
    for r in rows:
        res = conn.execute(
            """
            INSERT INTO aum_history (as_of_date, aum, currency, source, raw_id)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (as_of_date, source) DO NOTHING
            RETURNING id
            """,
            (r.as_of_date, r.aum, r.currency, r.source, raw_id),
        ).fetchone()
        if res:
            n += 1
    return n


# ---- collector_runs ------------------------------------------------------

def start_run(conn, collector: str, started_at: datetime) -> int:
    row = conn.execute(
        """
        INSERT INTO collector_runs (collector, started_at, status)
        VALUES (%s, %s, 'ok') RETURNING id
        """,
        (collector, started_at),
    ).fetchone()
    return row["id"]


def finish_run(
    conn,
    run_id: int,
    *,
    finished_at: datetime,
    status: str,
    new_raw: int = 0,
    new_rows: int = 0,
    error_msg: Optional[str] = None,
) -> None:
    conn.execute(
        """
        UPDATE collector_runs
           SET finished_at = %s, status = %s, new_raw = %s,
               new_rows = %s, error_msg = %s
         WHERE id = %s
        """,
        (finished_at, status, new_raw, new_rows, error_msg, run_id),
    )


def last_success_at(conn, collector: str) -> Optional[datetime]:
    row = conn.execute(
        """
        SELECT finished_at FROM collector_runs
         WHERE collector = %s AND status = 'ok'
         ORDER BY finished_at DESC NULLS LAST LIMIT 1
        """,
        (collector,),
    ).fetchone()
    return row["finished_at"] if row else None


# ---- changes -------------------------------------------------------------

def insert_change(
    conn,
    *,
    entity_type: str,
    change_type: str,
    entity_key: str,
    before: Optional[dict],
    after: Optional[dict],
    as_of_date: Optional[date],
) -> bool:
    """Insert a diff event. Deduped by (entity_type, entity_key, as_of_date,
    change_type). Returns True if a new row was inserted."""
    res = conn.execute(
        """
        INSERT INTO changes
          (entity_type, change_type, entity_key, before, after, as_of_date)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (entity_type, entity_key, as_of_date, change_type)
        DO NOTHING
        RETURNING id
        """,
        (
            entity_type, change_type, entity_key,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
            as_of_date,
        ),
    ).fetchone()
    return res is not None
