"""Backfill Korean 5% disclosures (DART 대량보유상황보고).

    python -m pipeline.backfill_kr --since 2015
    python -m pipeline.backfill_kr --since 2015 --manager burgundy

DART has no "what does this manager hold" endpoint: stakes are found by
scanning issuers that filed an ownership disclosure and keeping the rows whose
reporter name matches. The daily collector only scans the last few days, so a
stake disclosed before tracking started is never seen. This walks the same
scan over a multi-year window instead.

Idempotent — documents already stored are skipped on content hash — so it is
safe to re-run, and safe to widen the window later.

Costs API calls: one list.json page per 90-day chunk plus one majorstock.json
per issuer found. DART's daily quota is the limit to watch; ``--limit`` caps
the issuers processed in a single run so a large backfill can be split.
"""
from __future__ import annotations

import argparse
import os
from datetime import date

import config
from collectors.dart_5pct import Dart5pctCollector
from db.conn import connect
from pipeline import managers


def _env_int(name: str, default=None):
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill Korean 5% disclosures")
    ap.add_argument("--since", type=int,
                    default=_env_int("KR_BACKFILL_SINCE", 2015),
                    help="earliest disclosure year (env KR_BACKFILL_SINCE)")
    ap.add_argument("--limit", type=int, default=_env_int("KR_BACKFILL_LIMIT"),
                    help="max issuers per manager this run (env KR_BACKFILL_LIMIT)")
    ap.add_argument("--manager",
                    default=os.environ.get("KR_BACKFILL_MANAGER", "all").strip() or "all",
                    help="manager slug, or 'all' (env KR_BACKFILL_MANAGER)")
    args = ap.parse_args()

    if not config.DART_API_KEY:
        print("[backfill_kr] DART_API_KEY not set — nothing can be fetched")
        raise SystemExit(1)

    with connect() as conn:
        managers.sync_from_config(conn)
        targets = ([managers.by_slug(conn, args.manager)] if args.manager != "all"
                   else managers.active(conn))
    targets = [m for m in targets if m]
    if not targets:
        print(f"[backfill_kr] no such manager: {args.manager}")
        raise SystemExit(1)

    failed = []
    for m in targets:
        collector = Dart5pctCollector(m, since=date(args.since, 1, 1),
                                      limit=args.limit)
        if not collector.applies():
            print(f"[backfill_kr] {m['slug']}: no DART search terms; skipping")
            continue
        terms = ", ".join(m.get("dart_terms") or [])
        print(f"[backfill_kr] {m['slug']} (reporter matches: {terms}) "
              f"from {args.since} ...")
        try:
            result = collector.run()
        except Exception as exc:
            failed.append(m["slug"])
            print(f"[backfill_kr] {m['slug']} crashed: {exc}")
            continue
        if result.get("status") == "error":
            failed.append(m["slug"])
        with connect() as conn:
            held = conn.execute(
                "SELECT count(DISTINCT corp_code) c FROM kr_holdings"
                " WHERE manager_id = %s", (m["id"],)).fetchone()["c"]
        print(f"[backfill_kr] {m['slug']}: {result}; {held} Korean issuer(s) on file")

    if failed:
        print(f"[backfill_kr] finished with errors for: {', '.join(failed)}")
        raise SystemExit(1)
    print(f"[backfill_kr] done ({len(targets)} manager(s))")


if __name__ == "__main__":
    main()
