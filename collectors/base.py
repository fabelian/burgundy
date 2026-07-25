"""BaseCollector — common collection flow.

Concrete collectors implement ``discover``, ``fetch``, ``parse`` and
``persist``. ``run`` wires them together with idempotency, per-document error
isolation and ``collector_runs`` bookkeeping.
"""
from __future__ import annotations

import hashlib
import traceback
from datetime import datetime, timezone

from collectors.types import FetchTarget, RawDoc
from db.conn import connect
from pipeline import repo


def sha256_hex(payload: str | bytes) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BaseCollector:
    source: str = "base"

    def __init__(self, manager: dict):
        """``manager`` is a row from the ``managers`` table.

        Every collector instance belongs to exactly one manager: it is what
        scopes the idempotency checks, so two managers can hold the same
        security, or file identical boilerplate, without colliding.
        """
        self.manager = manager
        self.manager_id = manager["id"]

    def __repr__(self) -> str:  # shows up in logs
        return f"<{type(self).__name__} {self.manager['slug']}>"

    @property
    def log_prefix(self) -> str:
        return f"{self.manager['slug']}/{self.source}"

    def applies(self) -> bool:
        """Whether this manager has what the collector needs (id, url, key)."""
        return True

    # ---- to be implemented by subclasses --------------------------------
    def discover(self) -> list[FetchTarget]:
        """Return candidate documents (with idempotency keys)."""
        raise NotImplementedError

    def fetch(self, target: FetchTarget) -> RawDoc:
        """Download a target into a RawDoc (content_hash filled in)."""
        raise NotImplementedError

    def persist(self, conn, raw_id: int, raw_payload: str, target: FetchTarget) -> int:
        """Parse the raw payload, insert snapshot rows, generate diffs.

        Runs inside a transaction. Returns number of new snapshot rows.
        Subclasses delegate parsing to ``parsers/`` and diffs to ``pipeline.diff``.
        """
        raise NotImplementedError

    # ---- idempotency helpers --------------------------------------------
    def already_have_target(self, conn, target: FetchTarget) -> bool:
        """Skip a target we already fetched (by external_id when present)."""
        if target.external_id:
            return repo.external_id_seen(
                conn, self.manager_id, self.source, target.external_id)
        return False

    # ---- common flow ----------------------------------------------------
    def run(self) -> dict:
        started = _now()
        new_raw = 0
        new_rows = 0
        errors: list[str] = []

        with connect() as conn:
            run_id = repo.start_run(conn, self.manager_id, self.source, started)
        # start_run committed on context exit.

        try:
            targets = self.discover()
        except Exception as exc:  # discovery failure -> whole run errors
            with connect() as conn:
                repo.finish_run(
                    conn, run_id, finished_at=_now(), status="error",
                    error_msg=f"discover failed: {exc}",
                )
            print(f"[{self.log_prefix}] discover failed: {exc}")
            traceback.print_exc()
            return {"status": "error", "new_raw": 0, "new_rows": 0}

        for target in targets:
            try:
                with connect() as conn:
                    if self.already_have_target(conn, target):
                        continue
                    raw = self.fetch(target)
                    if raw is None:
                        continue
                    if repo.raw_exists(conn, self.manager_id, self.source,
                                       raw.content_hash):
                        # content unchanged since a prior fetch
                        continue
                    raw_id = repo.insert_raw(conn, self.manager_id, raw)
                    if raw_id is None:
                        continue
                    new_raw += 1
                    rows = self.persist(conn, raw_id, raw.payload, target)
                    new_rows += rows
            except Exception as exc:  # isolate per-document failures
                msg = f"{target.external_id or target.url}: {exc}"
                errors.append(msg)
                print(f"[{self.log_prefix}] item failed: {msg}")
                traceback.print_exc()

        status = "error" if errors else "ok"
        with connect() as conn:
            repo.finish_run(
                conn, run_id, finished_at=_now(), status=status,
                new_raw=new_raw, new_rows=new_rows,
                error_msg="; ".join(errors)[:2000] if errors else None,
            )
        print(f"[{self.log_prefix}] done status={status} "
              f"new_raw={new_raw} new_rows={new_rows}")
        return {"status": status, "new_raw": new_raw, "new_rows": new_rows}
