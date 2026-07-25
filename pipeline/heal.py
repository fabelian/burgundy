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
from parsers.parse_13f import unit_multiplier
from pipeline import managers, repo
from pipeline.reparse import heal_13f_aum


def _explain(conn, manager) -> None:
    """Print why each quarter got the multiplier it did.

    "corrected 0" is ambiguous on its own — it means the recomputed value
    matched what was stored, which is equally true when the numbers are right
    and when the unit could not be inferred and fell back to the filing date.
    This separates the two.
    """
    from types import SimpleNamespace

    quarters = conn.execute(
        "SELECT DISTINCT as_of_date FROM holdings WHERE manager_id = %s"
        " ORDER BY as_of_date DESC",
        (manager["id"],),
    ).fetchall()
    print(f"[heal] {manager['slug']}: {len(quarters)} quarter(s)")
    print(f"{'  as_of':<14}{'pos':>5}{'w/shares':>9}{'median $/sh':>13}"
          f"{'unit':>7}{'stored':>22}{'recomputed':>22}")
    for q in quarters:
        as_of = q["as_of_date"]
        best = repo.best_filing_for_quarter(conn, manager["id"], as_of)
        if best is None:
            continue
        hrows = conn.execute(
            "SELECT value_kusd, shares FROM holdings"
            " WHERE manager_id = %s AND accession_no = %s",
            (manager["id"], best["accession_no"]),
        ).fetchall()
        rows = [SimpleNamespace(value_kusd=r["value_kusd"], shares=r["shares"])
                for r in hrows]
        priced = sorted(r.value_kusd / r.shares for r in rows
                        if r.shares and r.shares > 0 and r.value_kusd > 0)
        median = priced[len(priced) // 2] if priced else None
        mult = unit_multiplier(rows, best["filed_at"])
        stored = conn.execute(
            "SELECT aum FROM aum_history WHERE manager_id = %s"
            "   AND source = '13f_total' AND as_of_date = %s",
            (manager["id"], as_of),
        ).fetchone()
        recomputed = sum(r.value_kusd for r in rows) * mult
        median_txt = f"{median:.4f}" if median is not None else "n/a"
        stored_txt = f"{float(stored['aum']):,.0f}" if stored else "-"
        print(f"  {str(as_of):<12}{len(rows):>5}{len(priced):>9}{median_txt:>13}"
              f"{'x' + str(mult):>7}{stored_txt:>22}{recomputed:>22,.0f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Recompute derived AUM rows")
    ap.add_argument("--manager",
                    default=os.environ.get("HEAL_MANAGER", "all").strip() or "all",
                    help="manager slug, or 'all' (env HEAL_MANAGER)")
    ap.add_argument("--explain", action="store_true",
                    default=bool(os.environ.get("HEAL_EXPLAIN", "").strip()),
                    help="show the unit decision per quarter (env HEAL_EXPLAIN)")
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
            if args.explain:
                _explain(conn, m)
            filled, corrected = heal_13f_aum(conn, m["id"])
            total_filled += filled
            total_corrected += corrected
            # Share coverage decides whether the unit came from the filing or
            # from the filing date, so it belongs next to the counts.
            cov = conn.execute(
                "SELECT count(*) AS n,"
                "       count(*) FILTER (WHERE shares > 0) AS priced"
                "  FROM holdings WHERE manager_id = %s",
                (m["id"],),
            ).fetchone()
            source = ("filing" if cov["priced"] else "filing DATE (no share counts)")
            print(f"[heal] {m['slug']}: filled {filled}, corrected {corrected}"
                  f" — {cov['priced']}/{cov['n']} positions priced,"
                  f" unit from {source}")

    print(f"[heal] done — {total_filled} filled, {total_corrected} corrected "
          f"across {len(targets)} manager(s)")


if __name__ == "__main__":
    main()
