"""Re-parse raw documents into snapshots without re-fetching.

Because ``raw_documents`` is immutable, snapshots can always be rebuilt from it.
Snapshot inserts are ON CONFLICT DO NOTHING, so reparse never duplicates rows;
it fills in anything a parser change would now produce.

Usage:
    python -m pipeline.reparse                 # all sources
    python -m pipeline.reparse --source edgar_13f
"""
from __future__ import annotations

import argparse
from datetime import date

from dateutil import parser as dateparse

from db.conn import connect
from parsers.parse_13f import compute_total_aum, parse_13f
from parsers.parse_dart import parse_dart_majorstock
from parsers.parse_website import parse_team, parse_aum
from pipeline import diff, managers, repo


def _reparse_13f(conn, manager_id: int) -> int:
    rows = conn.execute(
        """
        SELECT r.id AS raw_id, r.external_id, r.payload,
               h.as_of_date, h.filed_at, h.is_amendment
          FROM raw_documents r
          LEFT JOIN LATERAL (
              SELECT as_of_date, filed_at, is_amendment
                FROM holdings
               WHERE manager_id = r.manager_id
                 AND accession_no = r.external_id LIMIT 1
          ) h ON true
         WHERE r.source = 'edgar_13f' AND r.manager_id = %s
        """,
        (manager_id,),
    ).fetchall()
    total = 0
    for r in rows:
        if not r["as_of_date"]:
            # no prior snapshot to source metadata from; skip (needs collector)
            continue
        parsed = parse_13f(
            r["payload"], as_of_date=r["as_of_date"], filed_at=r["filed_at"],
            accession_no=r["external_id"], is_amendment=r["is_amendment"],
        )
        total += repo.insert_holdings(conn, manager_id, parsed, r["raw_id"])
        diff.diff_us_holdings(conn, manager_id, r["external_id"])
        aum = compute_total_aum(parsed, r["as_of_date"], r["filed_at"])
        if aum is not None:
            repo.insert_aum(conn, manager_id, [aum], r["raw_id"])
            diff.diff_aum(conn, manager_id, "13f_total", r["as_of_date"])
    return total


def heal_13f_aum(conn, manager_id: int) -> tuple[int, int]:
    """Recompute the 13f_total AUM series from stored holdings.

    Returns ``(filled, corrected)``.

    Fills quarters that have holdings but no AUM row: collectors skip
    already-fetched filings, so a derived series added after the holdings were
    first collected would otherwise never backfill.

    Also *corrects* a stored value that no longer matches what the current
    scaling rule produces. ``insert_aum`` is ON CONFLICT DO NOTHING and
    ``aum_history`` is UNIQUE per (manager, as_of_date, source), so a value under
    a wrong rule can only be repaired in place — the correction is recorded as
    an ``AUM_CORRECTED`` event so the audit trail survives the overwrite.

    Idempotent: a run that finds everything already correct changes nothing.
    """
    from types import SimpleNamespace

    quarters = conn.execute(
        "SELECT DISTINCT as_of_date FROM holdings"
        " WHERE manager_id = %s ORDER BY as_of_date",
        (manager_id,),
    ).fetchall()

    filled = corrected = 0
    for row in quarters:
        as_of = row["as_of_date"]
        best = repo.best_filing_for_quarter(conn, manager_id, as_of)
        if best is None:
            continue
        hrows = conn.execute(
            "SELECT value_kusd, raw_id FROM holdings"
            " WHERE manager_id = %s AND accession_no = %s",
            (manager_id, best["accession_no"]),
        ).fetchall()
        rows = [SimpleNamespace(value_kusd=r["value_kusd"]) for r in hrows]
        aum = compute_total_aum(rows, as_of, best["filed_at"])
        if aum is None:
            continue
        raw_id = next((r["raw_id"] for r in hrows if r["raw_id"] is not None), None)

        if repo.insert_aum(conn, manager_id, [aum], raw_id):
            diff.diff_aum(conn, manager_id, "13f_total", as_of)
            filled += 1
            continue

        stored = conn.execute(
            "SELECT aum FROM aum_history"
            " WHERE manager_id = %s AND source = '13f_total' AND as_of_date = %s",
            (manager_id, as_of),
        ).fetchone()
        if stored is None or float(stored["aum"]) == aum.aum:
            continue
        conn.execute(
            "UPDATE aum_history SET aum = %s, raw_id = COALESCE(%s, raw_id) "
            " WHERE manager_id = %s AND source = '13f_total' AND as_of_date = %s",
            (aum.aum, raw_id, manager_id, as_of),
        )
        repo.insert_change(
            conn,
            manager_id,
            entity_type="aum",
            change_type="AUM_CORRECTED",
            entity_key="13f_total",
            before={"aum": float(stored["aum"])},
            after={"aum": aum.aum},
            as_of_date=as_of,
        )
        corrected += 1
    return filled, corrected


def _reparse_dart(conn, manager_id: int) -> int:
    rows = conn.execute(
        "SELECT id AS raw_id, payload FROM raw_documents"
        " WHERE source = 'dart_5pct' AND manager_id = %s",
        (manager_id,),
    ).fetchall()
    total = 0
    for r in rows:
        parsed = parse_dart_majorstock(r["payload"])
        total += repo.insert_kr_holdings(conn, manager_id, parsed, r["raw_id"])
        for row in parsed:
            diff.diff_kr_holdings(conn, manager_id, row.rcept_no, row.corp_code)
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-parse raw documents")
    ap.add_argument("--source", default="all",
                    choices=["all", "edgar_13f", "dart_5pct"])
    ap.add_argument("--manager", default="all",
                    help="manager slug, or 'all' (default)")
    args = ap.parse_args()

    with connect() as conn:
        targets = ([managers.by_slug(conn, args.manager)] if args.manager != "all"
                   else managers.active(conn))
        targets = [m for m in targets if m]
        if not targets:
            print(f"[reparse] no such manager: {args.manager}")
            return
        total = 0
        for m in targets:
            if args.source in ("all", "edgar_13f"):
                total += _reparse_13f(conn, m["id"])
            if args.source in ("all", "dart_5pct"):
                total += _reparse_dart(conn, m["id"])
    print(f"[reparse] rebuilt {total} snapshot row(s) "
          f"across {len(targets)} manager(s)")


if __name__ == "__main__":
    main()
