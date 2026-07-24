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


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill historical 13F filings")
    ap.add_argument("--since", type=int, default=2013,
                    help="earliest report year to include (default 2013)")
    ap.add_argument("--limit", type=int, default=None,
                    help="max filings to process this run")
    args = ap.parse_args()

    collector = Edgar13FCollector(since=date(args.since, 1, 1), limit=args.limit)
    result = collector.run()
    print(f"[backfill] {result}")


if __name__ == "__main__":
    main()
