"""Fund fact-sheet collector.

discover: expand each tracked fund's URL template over recent periods
fetch:    download the PDF (404 = that period is not published yet)
persist:  parse_factsheet -> fund_holdings

This is the only route to a Korean large cap for these managers; the reasoning,
and the sources ruled out to get here, are in docs/korea-holdings.md.

The parser is not calibrated yet (no real document has been observed from the
development sandbox, which has no outbound access). Running anyway is the
point: fetching stores the original PDF in ``raw_documents``, and one stored
document is all ``parsers.parse_factsheet`` needs to be written against
something real. Until then a run reports new_raw > 0 with new_rows = 0, which
is visible on the dashboard's collector panel and is not the same signal as a
quiet period.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

from collectors.base import BaseCollector, sha256_hex
from collectors.http import get_binary
from collectors.types import FetchTarget, RawDoc
from db.conn import connect
from parsers.parse_factsheet import (
    FactsheetFormatUnknown,
    encode_payload,
    parse_factsheet,
)
from pipeline import funds as funds_registry
from pipeline import repo

# How far back to look for documents on each run, per cadence. Roughly two to
# three years each: enough to establish a trend without re-requesting a decade
# every week. Periods already fetched are skipped by external_id, so the cost
# after the first run is only the periods that have appeared since.
#
# The step is in months, and it is what makes a cadence real rather than a
# label. An MRFP is semi-annual, and treating one as quarterly would look for
# Q1 and Q3 documents that were never filed while labelling the ones that do
# exist with a quarter they do not cover.
_CADENCES = {
    "monthly":     {"step": 1,  "back": 24},
    "quarterly":   {"step": 3,  "back": 8},
    "semi-annual": {"step": 6,  "back": 6},
    "annual":      {"step": 12, "back": 3},
}


class UnknownCadence(ValueError):
    """A fund declares a publication cadence the expander does not model."""


def _quarter_of(month: int) -> int:
    return (month - 1) // 3 + 1


def _period_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _label(cadence: str, year: int, month: int) -> str:
    if cadence == "monthly":
        return f"{year}-{month:02d}"
    if cadence == "semi-annual":
        return f"{year}H{1 if month <= 6 else 2}"
    if cadence == "annual":
        return str(year)
    return f"{year}Q{_quarter_of(month)}"


def recent_periods(cadence: str, today: date,
                   count: Optional[int] = None) -> list[dict]:
    """Publication periods to look for, newest first.

    The current period is included even though its document may not exist yet —
    a fund that publishes early would otherwise go unread for a whole period,
    and a period that does not exist costs one 404.

    An unmodelled cadence raises rather than falling back to quarterly. Silently
    quartering a semi-annual filing yields labels naming periods the document
    does not cover, and a wrongly dated holding is worse than an uncollected one.
    """
    spec = _CADENCES.get(cadence)
    if spec is None:
        raise UnknownCadence(
            f"cadence {cadence!r} is not modelled; known: "
            f"{', '.join(sorted(_CADENCES))}")
    step = spec["step"]
    n = count if count is not None else spec["back"]

    out: list[dict] = []
    year, month = today.year, today.month
    if step > 1:
        # Snap to the end of the period currently in progress, so the newest
        # entry names a period rather than today's month.
        month = ((month - 1) // step + 1) * step
    for _ in range(n):
        out.append({
            "label": _label(cadence, year, month),
            "as_of": _period_end(year, month),
            "vars": {"q": _quarter_of(month), "yy": f"{year % 100:02d}",
                     "yyyy": str(year), "mm": f"{month:02d}",
                     "h": 1 if month <= 6 else 2},
        })
        month -= step
        while month <= 0:
            month += 12
            year -= 1
    return out


def expand_template(template: str, period: dict) -> str:
    return template.format(**period["vars"])


class FactsheetCollector(BaseCollector):
    source = "factsheet"

    def applies(self) -> bool:
        # A manager with no tracked fund document has nothing to fetch. Funds
        # are added to config.FUNDS once their URL has been seen, never guessed,
        # so most managers legitimately have none yet.
        return bool(self._funds())

    def _funds(self) -> list[dict]:
        with connect() as conn:
            rows = funds_registry.for_manager(conn, self.manager_id)
        return [f for f in rows
                if f.get("doc_url_template") or f.get("doc_url")]

    # ---- discover -------------------------------------------------------
    def discover(self) -> list[FetchTarget]:
        targets: list[FetchTarget] = []
        today = date.today()
        for fund in self._funds():
            if fund.get("doc_url_template"):
                # The period is in the path, so each one is a distinct document
                # and an external_id skips the ones already fetched.
                try:
                    periods = recent_periods(fund["cadence"], today)
                except UnknownCadence as exc:
                    # Isolated to the fund: one mistyped cadence must not blind
                    # the manager's other funds for the whole run.
                    print(f"[{self.log_prefix}] {fund['slug']}: {exc}; skipped")
                    periods = []
                for period in periods:
                    targets.append(FetchTarget(
                        source=self.source,
                        external_id=f"{fund['slug']}:{period['label']}",
                        url=expand_template(fund["doc_url_template"], period),
                        meta={"fund": fund, "period": period},
                    ))
            if fund.get("doc_url"):
                # One address whose contents are replaced each period. It must
                # carry *no* external_id: keyed by one, the first fetch would
                # mark it seen and every later quarter would be skipped
                # forever. With none, dedup falls to the content hash, so the
                # document is re-read each run and only a genuinely new edition
                # is stored — the same rule the DART collector uses.
                targets.append(FetchTarget(
                    source=self.source,
                    external_id=None,
                    url=fund["doc_url"],
                    meta={"fund": fund, "period": None},
                ))
        print(f"[{self.log_prefix}] {len(targets)} fund document(s) to check")
        return targets

    # ---- fetch ----------------------------------------------------------
    def fetch(self, target: FetchTarget) -> Optional[RawDoc]:
        data = get_binary(target.url)
        if data is None:
            return None                      # period not published
        payload = encode_payload(data)
        return RawDoc(
            source=self.source,
            external_id=target.external_id,
            url=target.url,
            payload=payload,
            # Hash the PDF bytes, not the base64 text: the same document
            # re-encoded must hash the same.
            content_hash=sha256_hex(data),
            meta=target.meta,
        )

    # ---- persist --------------------------------------------------------
    def persist(self, conn, raw_id, raw_payload, target) -> int:
        fund = target.meta["fund"]
        period = target.meta["period"]
        # A latest-only document states its own as-of date; there is no period
        # in its URL to label it with, and guessing one from today's date would
        # attach a fact sheet to a quarter it does not cover.
        label = period["label"] if period else "latest"
        try:
            doc = parse_factsheet(raw_payload, fund=fund, period_label=label)
        except FactsheetFormatUnknown as exc:
            # Deliberately not re-raised: the run must keep the fetched document
            # rather than roll it back, since that document is what unblocks the
            # parser. Returning 0 leaves new_raw > 0 / new_rows = 0 on the run.
            print(f"[{self.log_prefix}] {exc}")
            return 0
        # The fund's own NAV first: a weight is only meaningful against the
        # fund it is a weight of, and the tab reads the two together.
        repo.upsert_fund_snapshot(conn, self.manager_id, fund["id"],
                                  doc.snapshot, raw_id)
        return repo.insert_fund_holdings(conn, self.manager_id, fund["id"],
                                         doc.holdings, raw_id)
