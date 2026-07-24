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
from parsers.parse_13f import parse_13f
from parsers.parse_dart import parse_dart_majorstock
from parsers.parse_website import parse_team, parse_aum
from pipeline import diff, repo


def _reparse_13f(conn) -> int:
    rows = conn.execute(
        """
        SELECT r.id AS raw_id, r.external_id, r.payload,
               h.as_of_date, h.filed_at, h.is_amendment
          FROM raw_documents r
          LEFT JOIN LATERAL (
              SELECT as_of_date, filed_at, is_amendment
                FROM holdings WHERE accession_no = r.external_id LIMIT 1
          ) h ON true
         WHERE r.source = 'edgar_13f'
        """
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
        total += repo.insert_holdings(conn, parsed, r["raw_id"])
        diff.diff_us_holdings(conn, r["external_id"])
    return total


def _reparse_dart(conn) -> int:
    rows = conn.execute(
        "SELECT id AS raw_id, payload FROM raw_documents WHERE source = 'dart_5pct'"
    ).fetchall()
    total = 0
    for r in rows:
        parsed = parse_dart_majorstock(r["payload"])
        total += repo.insert_kr_holdings(conn, parsed, r["raw_id"])
        for row in parsed:
            diff.diff_kr_holdings(conn, row.rcept_no, row.corp_code)
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-parse raw documents")
    ap.add_argument("--source", default="all",
                    choices=["all", "edgar_13f", "dart_5pct"])
    args = ap.parse_args()

    with connect() as conn:
        total = 0
        if args.source in ("all", "edgar_13f"):
            total += _reparse_13f(conn)
        if args.source in ("all", "dart_5pct"):
            total += _reparse_dart(conn)
    print(f"[reparse] rebuilt {total} snapshot row(s)")


if __name__ == "__main__":
    main()
