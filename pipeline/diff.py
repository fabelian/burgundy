"""Snapshot comparison -> ``changes`` events.

Every function here must run inside the same transaction as the snapshot
insert that triggered it (the collector controls the transaction). Duplicate
events are prevented by the unique index on
``(entity_type, entity_key, as_of_date, change_type)`` and the ON CONFLICT in
``repo.insert_change``.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from collectors.types import PersonnelRow
from pipeline import repo


# ---------------------------------------------------------------------------
# US holdings (13F)
# ---------------------------------------------------------------------------

def _previous_accession(conn, as_of_date: date) -> Optional[str]:
    """Accession of the best snapshot strictly before ``as_of_date``.

    Picks the most recent prior quarter; within a quarter the latest-filed
    (amendment-preferred) filing wins.
    """
    row = conn.execute(
        """
        SELECT accession_no
          FROM holdings
         WHERE as_of_date < %s
         ORDER BY as_of_date DESC, filed_at DESC
         LIMIT 1
        """,
        (as_of_date,),
    ).fetchone()
    return row["accession_no"] if row else None


def _holdings_by_cusip(conn, accession_no: str) -> dict[str, dict]:
    rows = conn.execute(
        """
        SELECT cusip, name, shares, value_kusd, weight
          FROM holdings WHERE accession_no = %s
        """,
        (accession_no,),
    ).fetchall()
    return {r["cusip"]: r for r in rows}


def diff_us_holdings(conn, accession_no: str) -> int:
    """Compare a just-inserted 13F filing against the prior quarter."""
    meta = conn.execute(
        "SELECT as_of_date FROM holdings WHERE accession_no = %s LIMIT 1",
        (accession_no,),
    ).fetchone()
    if not meta:
        return 0
    as_of = meta["as_of_date"]

    prev_acc = _previous_accession(conn, as_of)
    current = _holdings_by_cusip(conn, accession_no)
    if prev_acc is None:
        return 0  # first filing ever: nothing to diff against
    previous = _holdings_by_cusip(conn, prev_acc)

    n = 0
    for cusip, cur in current.items():
        prev = previous.get(cusip)
        if prev is None:
            n += _emit_holding(conn, "NEW_POSITION", cusip, None, cur, as_of)
        else:
            if cur["shares"] > prev["shares"]:
                n += _emit_holding(conn, "INCREASED", cusip, prev, cur, as_of)
            elif cur["shares"] < prev["shares"]:
                n += _emit_holding(conn, "DECREASED", cusip, prev, cur, as_of)
    for cusip, prev in previous.items():
        if cusip not in current:
            n += _emit_holding(conn, "EXITED", cusip, prev, None, as_of)
    return n


def _emit_holding(conn, change_type, cusip, prev, cur, as_of) -> int:
    def _pack(r):
        if r is None:
            return None
        return {
            "name": r["name"],
            "shares": int(r["shares"]),
            "value_kusd": int(r["value_kusd"]),
            "weight": float(r["weight"]) if r["weight"] is not None else None,
        }

    inserted = repo.insert_change(
        conn,
        entity_type="us_holding",
        change_type=change_type,
        entity_key=cusip,
        before=_pack(prev),
        after=_pack(cur),
        as_of_date=as_of,
    )
    return 1 if inserted else 0


# ---------------------------------------------------------------------------
# Korean holdings (DART)
# ---------------------------------------------------------------------------

def diff_kr_holdings(conn, rcept_no: str, corp_code: str) -> int:
    """Compare the just-inserted DART report against the prior one for the corp."""
    cur = conn.execute(
        """
        SELECT as_of_date, corp_name, ownership_pct, shares
          FROM kr_holdings WHERE rcept_no = %s AND corp_code = %s
        """,
        (rcept_no, corp_code),
    ).fetchone()
    if not cur:
        return 0

    prev = conn.execute(
        """
        SELECT ownership_pct, shares FROM kr_holdings
         WHERE corp_code = %s AND as_of_date < %s
         ORDER BY as_of_date DESC, filed_at DESC LIMIT 1
        """,
        (corp_code, cur["as_of_date"]),
    ).fetchone()
    if not prev:
        return 0

    cur_pct = float(cur["ownership_pct"]) if cur["ownership_pct"] is not None else None
    prev_pct = float(prev["ownership_pct"]) if prev["ownership_pct"] is not None else None
    if cur_pct == prev_pct:
        return 0

    inserted = repo.insert_change(
        conn,
        entity_type="kr_holding",
        change_type="STAKE_CHANGED",
        entity_key=corp_code,
        before={"ownership_pct": prev_pct, "shares": _int_or_none(prev["shares"])},
        after={"ownership_pct": cur_pct, "shares": _int_or_none(cur["shares"]),
               "corp_name": cur["corp_name"]},
        as_of_date=cur["as_of_date"],
    )
    return 1 if inserted else 0


def _int_or_none(v):
    return int(v) if v is not None else None


# ---------------------------------------------------------------------------
# AUM
# ---------------------------------------------------------------------------

def diff_aum(conn, source: str, as_of_date: date) -> int:
    """Emit AUM_UPDATED if the new value differs from the prior value for source."""
    cur = conn.execute(
        "SELECT aum, currency FROM aum_history WHERE source = %s AND as_of_date = %s",
        (source, as_of_date),
    ).fetchone()
    if not cur:
        return 0
    prev = conn.execute(
        """
        SELECT aum, currency FROM aum_history
         WHERE source = %s AND as_of_date < %s
         ORDER BY as_of_date DESC LIMIT 1
        """,
        (source, as_of_date),
    ).fetchone()
    if not prev:
        return 0
    if float(cur["aum"]) == float(prev["aum"]):
        return 0
    inserted = repo.insert_change(
        conn,
        entity_type="aum",
        change_type="AUM_UPDATED",
        entity_key=source,
        before={"aum": float(prev["aum"]), "currency": prev["currency"]},
        after={"aum": float(cur["aum"]), "currency": cur["currency"]},
        as_of_date=as_of_date,
    )
    return 1 if inserted else 0


# ---------------------------------------------------------------------------
# Personnel (SCD Type 2)
# ---------------------------------------------------------------------------

def reconcile_personnel(
    conn,
    source: str,
    scraped: list[PersonnelRow],
    as_of: date,
    raw_id: Optional[int],
) -> int:
    """Reconcile a fresh scrape against the currently-valid personnel set.

    * new person          -> PERSON_JOINED  + new SCD row (valid_to NULL)
    * disappeared person  -> PERSON_LEFT    + close current row (valid_to = as_of)
    * title changed       -> TITLE_CHANGED  + close old row, open new row
    """
    current = conn.execute(
        """
        SELECT id, person_name, title FROM personnel
         WHERE source = %s AND valid_to IS NULL
        """,
        (source,),
    ).fetchall()
    current_by_name = {r["person_name"]: r for r in current}
    scraped_by_name = {p.person_name: p for p in scraped}

    events = 0

    # joins & title changes
    for name, p in scraped_by_name.items():
        existing = current_by_name.get(name)
        if existing is None:
            _open_row(conn, p, as_of, raw_id)
            events += _emit_person(conn, "PERSON_JOINED", name, None,
                                   {"title": p.title}, as_of)
        elif existing["title"] != p.title:
            _close_row(conn, existing["id"], as_of)
            _open_row(conn, p, as_of, raw_id)
            events += _emit_person(conn, "TITLE_CHANGED", name,
                                   {"title": existing["title"]},
                                   {"title": p.title}, as_of)

    # departures
    for name, existing in current_by_name.items():
        if name not in scraped_by_name:
            _close_row(conn, existing["id"], as_of)
            events += _emit_person(conn, "PERSON_LEFT", name,
                                   {"title": existing["title"]}, None, as_of)
    return events


def _open_row(conn, p: PersonnelRow, valid_from: date, raw_id: Optional[int]) -> None:
    conn.execute(
        """
        INSERT INTO personnel (person_name, title, source, valid_from, valid_to, raw_id)
        VALUES (%s, %s, %s, %s, NULL, %s)
        """,
        (p.person_name, p.title, p.source, valid_from, raw_id),
    )


def _close_row(conn, row_id: int, valid_to: date) -> None:
    conn.execute(
        "UPDATE personnel SET valid_to = %s WHERE id = %s AND valid_to IS NULL",
        (valid_to, row_id),
    )


def _emit_person(conn, change_type, name, before, after, as_of) -> int:
    inserted = repo.insert_change(
        conn,
        entity_type="personnel",
        change_type=change_type,
        entity_key=name,
        before=before,
        after=after,
        as_of_date=as_of,
    )
    return 1 if inserted else 0
