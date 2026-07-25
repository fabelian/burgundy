"""Recompute the derived 13f_total AUM series from stored holdings.

    python -m pipeline.heal
    python -m pipeline.heal --manager beutel-goodman

A parser change only reaches the dashboard once something recomputes the
derived rows, and the two paths that do — a collection cycle and a backfill —
both talk to SEC first. This one touches nothing but the database, so a scaling
fix can be applied to years of history in seconds without re-fetching a single
filing.

Corrections are recorded as ``AUM_CORRECTED`` change events, same as when the
collector heals them.
"""
from __future__ import annotations

import argparse
import os

from db.conn import connect
from pipeline import managers
from pipeline.reparse import heal_13f_aum


def main() -> None:
    ap = argparse.ArgumentParser(description="Recompute derived AUM rows")
    ap.add_argument("--manager",
                    default=os.environ.get("HEAL_MANAGER", "all").strip() or "all",
                    help="manager slug, or 'all' (env HEAL_MANAGER)")
    args = ap.parse_args()

    with connect() as conn:
        managers.sync_from_config(conn)
        targets = ([managers.by_slug(conn, args.manager)] if args.manager != "all"
                   else managers.active(conn))
        targets = [m for m in targets if m]
        if not targets:
            print(f"[heal] no such manager: {args.manager}")
            raise SystemExit(1)

        total_filled = total_corrected = 0
        for m in targets:
            filled, corrected = heal_13f_aum(conn, m["id"])
            total_filled += filled
            total_corrected += corrected
            print(f"[heal] {m['slug']}: filled {filled}, corrected {corrected}")

    print(f"[heal] done — {total_filled} filled, {total_corrected} corrected "
          f"across {len(targets)} manager(s)")


if __name__ == "__main__":
    main()
