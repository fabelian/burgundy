"""Cron entrypoint.

    python -m pipeline.run

Runs every collector. EDGAR and DART run each invocation; Form ADV and the
website collectors are skipped when their last successful run is within
WEEKLY_REFRESH_DAYS (checked via collector_runs). New change events are pushed
to Telegram if configured.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import config
from collectors.dart_5pct import Dart5pctCollector
from collectors.edgar_13f import Edgar13FCollector
from collectors.form_adv import FormAdvCollector
from collectors.website import WebsiteAumCollector, WebsiteTeamCollector
from db.conn import connect
from pipeline import notify, repo
from pipeline.reparse import heal_13f_aum

# (collector instance, weekly?) — weekly ones honour the skip window.
COLLECTORS = [
    (Edgar13FCollector(), False),
    (Dart5pctCollector(), False),
    (FormAdvCollector(), True),
    (WebsiteAumCollector(), True),
    (WebsiteTeamCollector(), True),
]


def _should_skip_weekly(source: str) -> bool:
    with connect() as conn:
        last = repo.last_success_at(conn, source)
    if last is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.WEEKLY_REFRESH_DAYS)
    return last > cutoff


def _record_skip(source: str) -> None:
    now = datetime.now(timezone.utc)
    with connect() as conn:
        run_id = repo.start_run(conn, source, now)
    with connect() as conn:
        repo.finish_run(conn, run_id, finished_at=now, status="skipped")
    print(f"[{source}] skipped (within {config.WEEKLY_REFRESH_DAYS}d refresh window)")


def _new_changes_since(started: datetime) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT entity_type, change_type, entity_key, as_of_date "
            "FROM changes WHERE detected_at >= %s ORDER BY id",
            (started,),
        ).fetchall()
    return rows


def main() -> None:
    run_started = datetime.now(timezone.utc)
    for collector, weekly in COLLECTORS:
        if weekly and _should_skip_weekly(collector.source):
            _record_skip(collector.source)
            continue
        try:
            collector.run()
        except Exception as exc:  # collector.run already records to DB; log here
            print(f"[run] collector {collector.source} crashed: {exc}")

    # self-heal: backfill any derived 13f_total AUM the collectors skipped
    try:
        with connect() as conn:
            healed, corrected = heal_13f_aum(conn)
            h_count = conn.execute("SELECT count(*) c FROM holdings").fetchone()["c"]
            a_count = conn.execute(
                "SELECT count(*) c FROM aum_history WHERE source='13f_total'"
            ).fetchone()["c"]
        print(f"[run] 13f_total heal: filled {healed} quarter(s), "
              f"corrected {corrected}; "
              f"holdings_rows={h_count} 13f_total_aum_rows={a_count}")
    except Exception as exc:
        print(f"[run] 13f_total heal failed: {exc}")

    changes = _new_changes_since(run_started)
    if changes and notify.enabled():
        lines = [notify.format_change(c) for c in changes[:30]]
        header = f"Burgundy tracker: {len(changes)} change(s) detected"
        notify.send(header + "\n" + "\n".join(lines))
    print(f"[run] complete; {len(changes)} new change event(s)")


if __name__ == "__main__":
    main()
