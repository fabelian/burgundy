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
    FundHoldingRow,
    HoldingRow,
    KrHoldingRow,
    PersonnelRow,
    ProxyVoteRow,
    RawDoc,
)


# ---- raw_documents -------------------------------------------------------

def insert_raw(conn, manager_id: int, doc: RawDoc) -> Optional[int]:
    """Insert a raw document. Returns its id, or the existing id on conflict.

    None is returned only if the row exists and we could not read it back
    (should not happen). Idempotency key: (manager_id, source, content_hash) —
    two managers filing identical content must not share a row.
    """
    row = conn.execute(
        """
        INSERT INTO raw_documents
              (manager_id, source, external_id, url, content_hash, payload)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (manager_id, source, content_hash) DO NOTHING
        RETURNING id
        """,
        (manager_id, doc.source, doc.external_id, doc.url, doc.content_hash,
         doc.payload),
    ).fetchone()
    if row:
        return row["id"]
    existing = conn.execute(
        "SELECT id FROM raw_documents"
        " WHERE manager_id = %s AND source = %s AND content_hash = %s",
        (manager_id, doc.source, doc.content_hash),
    ).fetchone()
    return existing["id"] if existing else None


def raw_exists(conn, manager_id: int, source: str, content_hash: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM raw_documents"
        " WHERE manager_id = %s AND source = %s AND content_hash = %s",
        (manager_id, source, content_hash),
    ).fetchone()
    return row is not None


def external_id_seen(conn, manager_id: int, source: str, external_id: str) -> bool:
    """True if a raw doc with this source/external_id already exists."""
    row = conn.execute(
        "SELECT 1 FROM raw_documents"
        " WHERE manager_id = %s AND source = %s AND external_id = %s LIMIT 1",
        (manager_id, source, external_id),
    ).fetchone()
    return row is not None


# ---- holdings (13F) ------------------------------------------------------

# A 13F-HR/A may restate the whole portfolio or only part of it, and the form
# itself does not say which in the information table. Taking the latest filing
# unconditionally lets a two-position amendment stand in for a hundred-position
# portfolio. A filing holding less than this share of the quarter's fullest
# position count is therefore not treated as a portfolio view at all — while a
# genuine restatement, which lists comparably many positions, still wins on
# recency.
_COMPLETENESS_FLOOR = 0.5


def best_filing_for_quarter(conn, manager_id: int, as_of: date) -> Optional[dict]:
    """The filing that best represents a quarter's portfolio.

    Latest filed wins (amendment preferred on a tie), among filings complete
    enough to be a portfolio — see ``_COMPLETENESS_FLOOR``. Returns None when
    the quarter has no holdings.
    """
    return conn.execute(
        """
        WITH f AS (
            SELECT accession_no, filed_at, is_amendment, count(*) AS positions
              FROM holdings WHERE manager_id = %s AND as_of_date = %s
             GROUP BY accession_no, filed_at, is_amendment
        )
        SELECT accession_no, filed_at, is_amendment, positions,
               (SELECT count(*) FROM f) AS filings
          FROM f
         WHERE positions >= (SELECT max(positions) FROM f) * %s
         ORDER BY filed_at DESC, is_amendment DESC
         LIMIT 1
        """,
        (manager_id, as_of, _COMPLETENESS_FLOOR),
    ).fetchone()


def insert_holdings(conn, manager_id: int, rows: Iterable[HoldingRow],
                    raw_id: Optional[int]) -> int:
    n = 0
    for r in rows:
        res = conn.execute(
            """
            INSERT INTO holdings
              (manager_id, as_of_date, filed_at, accession_no, is_amendment,
               cusip, ticker, name, shares, value_kusd, weight, raw_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (manager_id, accession_no, cusip) DO NOTHING
            RETURNING id
            """,
            (
                manager_id,
                r.as_of_date, r.filed_at, r.accession_no, r.is_amendment, r.cusip,
                r.ticker, r.name, r.shares, r.value_kusd, r.weight, raw_id,
            ),
        ).fetchone()
        if res:
            n += 1
    return n


# ---- filing_notices (13F-NT) --------------------------------------------

def insert_notice(
    conn,
    manager_id: int,
    *,
    as_of_date,
    filed_at,
    accession_no: str,
    form: str,
    report_type: Optional[str],
    other_managers: Optional[str],
    raw_id: Optional[int],
) -> bool:
    """Insert a 13F-NT notice record. Idempotent on accession_no."""
    res = conn.execute(
        """
        INSERT INTO filing_notices
          (manager_id, as_of_date, filed_at, accession_no, form, report_type,
           other_managers, raw_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (manager_id, accession_no) DO NOTHING
        RETURNING id
        """,
        (manager_id, as_of_date, filed_at, accession_no, form, report_type,
         other_managers, raw_id),
    ).fetchone()
    return res is not None


# ---- kr_holdings (DART) --------------------------------------------------

def insert_kr_holdings(conn, manager_id: int, rows: Iterable[KrHoldingRow],
                       raw_id: Optional[int]) -> int:
    n = 0
    for r in rows:
        res = conn.execute(
            """
            INSERT INTO kr_holdings
              (manager_id, as_of_date, filed_at, rcept_no, corp_code, corp_name,
               ticker, shares, ownership_pct, report_type, raw_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (manager_id, rcept_no, corp_code) DO NOTHING
            RETURNING id
            """,
            (
                manager_id,
                r.as_of_date, r.filed_at, r.rcept_no, r.corp_code, r.corp_name,
                r.ticker, r.shares, r.ownership_pct, r.report_type, raw_id,
            ),
        ).fetchone()
        if res:
            n += 1
    return n


# ---- fund_holdings (fact sheets) -----------------------------------------

def insert_fund_holdings(conn, manager_id: int, fund_id: int,
                         rows: Iterable[FundHoldingRow],
                         raw_id: Optional[int]) -> int:
    """Insert a fund document's positions.

    Idempotent on (fund_id, as_of_date, security_key). A re-fetch of the same
    document is therefore a no-op, but a *corrected* document — a manager
    re-issuing a fact sheet with a fixed weight — must not leave the old number
    standing, so a conflicting row is updated rather than ignored. That differs
    from the 13F path, where an amendment arrives under its own accession number
    and the two versions are both worth keeping.
    """
    n = 0
    for r in rows:
        res = conn.execute(
            """
            INSERT INTO fund_holdings
              (manager_id, fund_id, as_of_date, published_at, security_key,
               security_name, ticker, isin, country, is_korean, weight,
               market_value, currency, position_rank, disclosure_scope,
               positions_listed, raw_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (fund_id, as_of_date, security_key) DO UPDATE SET
                security_name    = EXCLUDED.security_name,
                ticker           = COALESCE(EXCLUDED.ticker, fund_holdings.ticker),
                isin             = COALESCE(EXCLUDED.isin, fund_holdings.isin),
                country          = COALESCE(EXCLUDED.country, fund_holdings.country),
                is_korean        = EXCLUDED.is_korean,
                weight           = EXCLUDED.weight,
                market_value     = EXCLUDED.market_value,
                currency         = COALESCE(EXCLUDED.currency, fund_holdings.currency),
                position_rank    = EXCLUDED.position_rank,
                disclosure_scope = EXCLUDED.disclosure_scope,
                positions_listed = EXCLUDED.positions_listed,
                raw_id           = EXCLUDED.raw_id
            RETURNING (xmax = 0) AS inserted
            """,
            (
                manager_id, fund_id, r.as_of_date, r.published_at, r.security_key,
                r.security_name, r.ticker, r.isin, r.country, bool(r.is_korean),
                r.weight, r.market_value, r.currency, r.position_rank,
                r.disclosure_scope, r.positions_listed, raw_id,
            ),
        ).fetchone()
        # xmax = 0 marks a genuine insert; an update leaves it set. Counting
        # updates as new rows would report a re-issued fact sheet as fresh
        # coverage.
        if res and res["inserted"]:
            n += 1
    return n


# ---- proxy_votes (NI 81-106 voting records) ------------------------------

def insert_proxy_votes(conn, manager_id: int, fund_id: int,
                       rows: Iterable[ProxyVoteRow],
                       raw_id: Optional[int]) -> int:
    """Insert a voting record's meetings.

    Plain DO NOTHING on conflict, unlike ``insert_fund_holdings``: a meeting on
    a given date is a historical fact that does not get restated, so a re-fetch
    has nothing to correct.
    """
    n = 0
    for r in rows:
        res = conn.execute(
            """
            INSERT INTO proxy_votes
              (manager_id, fund_id, period_ended, meeting_date, security_key,
               issuer_name, ticker, country, is_korean, ballots, raw_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (fund_id, meeting_date, security_key) DO NOTHING
            RETURNING id
            """,
            (manager_id, fund_id, r.period_ended, r.meeting_date, r.security_key,
             r.issuer_name, r.ticker, r.country, bool(r.is_korean), r.ballots,
             raw_id),
        ).fetchone()
        if res:
            n += 1
    return n


# ---- aum_history ---------------------------------------------------------

def insert_aum(conn, manager_id: int, rows: Iterable[AumRow],
               raw_id: Optional[int]) -> int:
    n = 0
    for r in rows:
        res = conn.execute(
            """
            INSERT INTO aum_history
              (manager_id, as_of_date, aum, currency, source, raw_id)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (manager_id, as_of_date, source) DO NOTHING
            RETURNING id
            """,
            (manager_id, r.as_of_date, r.aum, r.currency, r.source, raw_id),
        ).fetchone()
        if res:
            n += 1
    return n


# ---- collector_runs ------------------------------------------------------

def start_run(conn, manager_id: int, collector: str,
              started_at: datetime) -> int:
    row = conn.execute(
        """
        INSERT INTO collector_runs (manager_id, collector, started_at, status)
        VALUES (%s, %s, %s, 'ok') RETURNING id
        """,
        (manager_id, collector, started_at),
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


def last_success_at(conn, manager_id: int,
                    collector: str) -> Optional[datetime]:
    row = conn.execute(
        """
        SELECT finished_at FROM collector_runs
         WHERE manager_id = %s AND collector = %s AND status = 'ok'
         ORDER BY finished_at DESC NULLS LAST LIMIT 1
        """,
        (manager_id, collector),
    ).fetchone()
    return row["finished_at"] if row else None


# ---- changes -------------------------------------------------------------

def insert_change(
    conn,
    manager_id: int,
    *,
    entity_type: str,
    change_type: str,
    entity_key: str,
    before: Optional[dict],
    after: Optional[dict],
    as_of_date: Optional[date],
) -> bool:
    """Insert a diff event. Deduped per manager by (entity_type, entity_key,
    as_of_date, change_type). Returns True if a new row was inserted."""
    res = conn.execute(
        """
        INSERT INTO changes
          (manager_id, entity_type, change_type, entity_key, before, after,
           as_of_date)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (manager_id, entity_type, entity_key, as_of_date, change_type)
        DO NOTHING
        RETURNING id
        """,
        (
            manager_id, entity_type, change_type, entity_key,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
            as_of_date,
        ),
    ).fetchone()
    return res is not None
