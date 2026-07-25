"""Backfill historical 13F filings.

Usage:
    python -m pipeline.backfill --since 2015
    python -m pipeline.backfill --since 2015 --limit 20
    python -m pipeline.backfill --manager mawer

Reuses the normal collector flow, so it is idempotent: filings already stored
are skipped. Diffs are generated as each quarter is inserted, and the derived
``13f_total`` AUM series is healed per manager at the end, so a backfilled
manager is complete without waiting for the nightly run.

Every option also reads an environment variable (``BACKFILL_MANAGER``,
``BACKFILL_SINCE``, ``BACKFILL_LIMIT``). A deploy platform that runs a fixed
start command can then target one manager by setting a variable, instead of
needing a separate config file per manager.
"""
from __future__ import annotations

import argparse
import os
from datetime import date

from collectors.edgar_13f import Edgar13FCollector
from db.conn import connect
from pipeline import managers
from pipeline.reparse import heal_13f_aum


def _env_int(name: str, default=None):
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill historical 13F filings")
    ap.add_argument("--since", type=int, default=_env_int("BACKFILL_SINCE", 2013),
                    help="earliest report year to include (env BACKFILL_SINCE)")
    ap.add_argument("--limit", type=int, default=_env_int("BACKFILL_LIMIT"),
                    help="max filings per manager this run (env BACKFILL_LIMIT)")
    ap.add_argument("--manager",
                    default=os.environ.get("BACKFILL_MANAGER", "all").strip() or "all",
                    help="manager slug, or 'all' (env BACKFILL_MANAGER)")
    args = ap.parse_args()

    with connect() as conn:
        managers.sync_from_config(conn)
        targets = ([managers.by_slug(conn, args.manager)] if args.manager != "all"
                   else managers.active(conn))
    targets = [m for m in targets if m]
    if not targets:
        print(f"[backfill] no such manager: {args.manager}")
        raise SystemExit(1)

    print(f"[backfill] since={args.since} limit={args.limit} "
          f"managers={[m['slug'] for m in targets]}")

    failed = []
    for m in targets:
        collector = Edgar13FCollector(m, since=date(args.since, 1, 1),
                                      limit=args.limit)
        if not collector.applies():
            print(f"[backfill] {m['slug']}: no CIK on file; skipping")
            continue
        print(f"[backfill] {m['slug']} (CIK {m['cik']}) ...")
        try:
            result = collector.run()
        except Exception as exc:
            # One manager's failure must not cost the others their backfill.
            failed.append(m["slug"])
            print(f"[backfill] {m['slug']} crashed: {exc}")
            continue
        if result.get("status") == "error":
            failed.append(m["slug"])
        with connect() as conn:
            filled, corrected = heal_13f_aum(conn, m["id"])
            quarters = conn.execute(
                "SELECT count(DISTINCT as_of_date) c FROM holdings"
                " WHERE manager_id = %s", (m["id"],)).fetchone()["c"]
        print(f"[backfill] {m['slug']}: {result}; "
              f"13f_total filled={filled} corrected={corrected}; "
              f"quarters={quarters}")

    if failed:
        print(f"[backfill] finished with errors for: {', '.join(failed)}")
        raise SystemExit(1)
    print(f"[backfill] done ({len(targets)} manager(s))")


if __name__ == "__main__":
    main()
