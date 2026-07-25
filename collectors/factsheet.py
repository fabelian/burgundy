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

# How far back to look for documents on each run. Two years of quarters is
# enough to establish a trend line without re-requesting a decade every week;
# periods already fetched are skipped by external_id, so the cost after the
# first run is only the periods that have appeared since.
_QUARTERS_BACK = 8
_MONTHS_BACK = 24


def _quarter_of(month: int) -> int:
    return (month - 1) // 3 + 1


def _period_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def recent_periods(cadence: str, today: date,
                   count: Optional[int] = None) -> list[dict]:
    """Publication periods to look for, newest first.

    The current period is included even though its document may not exist yet —
    a fund that publishes early would otherwise go unread for three months, and
    a missing period costs one 404.
    """
    monthly = cadence == "monthly"
    n = count if count is not None else (_MONTHS_BACK if monthly else _QUARTERS_BACK)
    out: list[dict] = []
    year, month = today.year, today.month
    if not monthly:
        month = _quarter_of(month) * 3      # snap to the quarter-end month
    for _ in range(n):
        quarter = _quarter_of(month)
        out.append({
            "label": f"{year}-{month:02d}" if monthly else f"{year}Q{quarter}",
            "as_of": _period_end(year, month),
            "vars": {"q": quarter, "yy": f"{year % 100:02d}",
                     "yyyy": str(year), "mm": f"{month:02d}"},
        })
        step = 1 if monthly else 3
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
        return [f for f in rows if f.get("doc_url_template")]

    # ---- discover -------------------------------------------------------
    def discover(self) -> list[FetchTarget]:
        targets: list[FetchTarget] = []
        today = date.today()
        for fund in self._funds():
            for period in recent_periods(fund["cadence"], today):
                targets.append(FetchTarget(
                    source=self.source,
                    external_id=f"{fund['slug']}:{period['label']}",
                    url=expand_template(fund["doc_url_template"], period),
                    meta={"fund": fund, "period": period},
                ))
        print(f"[{self.log_prefix}] {len(targets)} fund-period document(s) to check")
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
        try:
            rows = parse_factsheet(raw_payload, fund=fund,
                                   period_label=period["label"])
        except FactsheetFormatUnknown as exc:
            # Deliberately not re-raised: the run must keep the fetched document
            # rather than roll it back, since that document is what unblocks the
            # parser. Returning 0 leaves new_raw > 0 / new_rows = 0 on the run.
            print(f"[{self.log_prefix}] {exc}")
            return 0
        return repo.insert_fund_holdings(conn, self.manager_id, fund["id"],
                                         rows, raw_id)
