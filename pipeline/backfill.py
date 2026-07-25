"""Backfill historical 13F filings.

Usage:
    python -m pipeline.backfill --since 2015
    python -m pipeline.backfill --since 2015 --limit 20

Reuses the normal collector flow, so it is idempotent: filings already stored
are skipped. Diffs are generated as each quarter is inserted.
"""
from __future__ import annotations

import argparse
from datetime import date

from collectors.edgar_13f import Edgar13FCollector
from db.conn import connect
from pipeline import managers


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill historical 13F filings")
    ap.add_argument("--since", type=int, default=2013,
                    help="earliest report year to include (default 2013)")
    ap.add_argument("--limit", type=int, default=None,
                    help="max filings to process this run")
    ap.add_argument("--manager", default="all",
                    help="manager slug, or 'all' (default)")
    args = ap.parse_args()

    with connect() as conn:
        managers.sync_from_config(conn)
        targets = ([managers.by_slug(conn, args.manager)] if args.manager != "all"
                   else managers.active(conn))
    targets = [m for m in targets if m]
    if not targets:
        print(f"[backfill] no such manager: {args.manager}")
        return

    for m in targets:
        collector = Edgar13FCollector(m, since=date(args.since, 1, 1),
                                      limit=args.limit)
        if not collector.applies():
            print(f"[backfill] {m['slug']}: no CIK on file; skipping")
            continue
        print(f"[backfill] {m['slug']} (CIK {m['cik']}) ...")
        print(f"[backfill] {m['slug']}: {collector.run()}")


if __name__ == "__main__":
    main()
