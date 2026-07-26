"""Cron entrypoint.

    python -m pipeline.run

Runs every collector for every tracked manager. EDGAR and DART run each
invocation; Form ADV and the website collectors are skipped when their last
successful run for that manager is within WEEKLY_REFRESH_DAYS (checked via
collector_runs). New change events are pushed to Telegram if configured.

A manager missing what a collector needs — no CIK, no CRD, no website URL, no
DART search terms — is passed over rather than guessed at.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import config
from collectors.dart_5pct import Dart5pctCollector
from collectors.edgar_13f import Edgar13FCollector
from collectors.factsheet import FactsheetCollector
from collectors.form_adv import FormAdvCollector
from collectors.website import WebsiteAumCollector, WebsiteTeamCollector
from db.conn import connect
from pipeline import funds, managers, notify, repo
from pipeline.reparse import heal_13f_aum

# (collector class, weekly?) — weekly ones honour the skip window.
# Fact sheets are published quarterly or monthly, so a daily fetch would ask a
# manager's site for the same unchanged PDF six extra times a week.
COLLECTORS = [
    (Edgar13FCollector, False),
    (Dart5pctCollector, False),
    (FactsheetCollector, True),
    (FormAdvCollector, True),
    (WebsiteAumCollector, True),
    (WebsiteTeamCollector, True),
]


def _should_skip_weekly(manager_id: int, source: str) -> bool:
    with connect() as conn:
        last = repo.last_success_at(conn, manager_id, source)
    if last is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.WEEKLY_REFRESH_DAYS)
    return last > cutoff


def _record_skip(manager, source: str, reason: str) -> None:
    now = datetime.now(timezone.utc)
    with connect() as conn:
        run_id = repo.start_run(conn, manager["id"], source, now)
    with connect() as conn:
        repo.finish_run(conn, run_id, finished_at=now, status="skipped")
    print(f"[{manager['slug']}/{source}] skipped ({reason})")


def _new_changes_since(started: datetime) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT m.name AS manager, c.entity_type, c.change_type, "
            "       c.entity_key, c.as_of_date "
            "  FROM changes c JOIN managers m ON m.id = c.manager_id "
            " WHERE c.detected_at >= %s ORDER BY c.id",
            (started,),
        ).fetchall()
    return rows


def _heal(manager) -> None:
    try:
        with connect() as conn:
            healed, corrected = heal_13f_aum(conn, manager["id"])
            h_count = conn.execute(
                "SELECT count(*) c FROM holdings WHERE manager_id = %s",
                (manager["id"],)).fetchone()["c"]
            a_count = conn.execute(
                "SELECT count(*) c FROM aum_history"
                " WHERE manager_id = %s AND source='13f_total'",
                (manager["id"],)).fetchone()["c"]
        print(f"[{manager['slug']}] 13f_total heal: filled {healed} quarter(s), "
              f"corrected {corrected}; "
              f"holdings_rows={h_count} 13f_total_aum_rows={a_count}")
    except Exception as exc:
        print(f"[{manager['slug']}] 13f_total heal failed: {exc}")


def main() -> None:
    run_started = datetime.now(timezone.utc)

    with connect() as conn:
        written = managers.sync_from_config(conn)
        fund_rows = funds.sync_from_config(conn)
        tracked = managers.active(conn)
    print(f"[run] {len(tracked)} manager(s) tracked ({written} synced from config); "
          f"{fund_rows} fund(s) synced")

    for manager in tracked:
        for cls, weekly in COLLECTORS:
            collector = cls(manager)
            if not collector.applies():
                _record_skip(manager, collector.source, "not configured for this manager")
                continue
            if weekly and _should_skip_weekly(manager["id"], collector.source):
                _record_skip(manager, collector.source,
                             f"within {config.WEEKLY_REFRESH_DAYS}d refresh window")
                continue
            try:
                collector.run()
            except Exception as exc:  # collector.run already records to DB
                print(f"[run] {manager['slug']}/{collector.source} crashed: {exc}")

        # self-heal: backfill/correct the derived 13f_total AUM for this manager
        _heal(manager)

    changes = _new_changes_since(run_started)
    if changes and notify.enabled():
        lines = [notify.format_change(c) for c in changes[:30]]
        header = f"Manager tracker: {len(changes)} change(s) detected"
        notify.send(header + "\n" + "\n".join(lines))
    print(f"[run] complete; {len(changes)} new change event(s)")


if __name__ == "__main__":
    main()
