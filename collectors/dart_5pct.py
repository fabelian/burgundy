"""DART 5% (대량보유상황보고) collector.

discover: list.json daily scan -> issuers with a major-holding disclosure
fetch:    majorstock.json(corp_code) -> all 5% holders for that issuer
persist:  parse_dart -> keep Burgundy rows -> kr_holdings insert -> diff
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import config
from collectors.base import BaseCollector, sha256_hex
from collectors.http import get_json
from collectors.types import FetchTarget, RawDoc
from parsers.parse_dart import parse_dart_majorstock
from pipeline import diff, repo

# disclosure type D = 지분공시 (ownership disclosures)
_MAJOR_HOLDING_KEYWORDS = ("대량보유", "주식등의")

# A list.json response is capped, so long windows are chunked and paged.
_WINDOW_DAYS = 90
_MAX_PAGES = 100

# list.json 세부유형: 주식등의 대량보유상황보고서
_DETAIL_MAJOR_HOLDING = "D001"


class DartError(RuntimeError):
    """DART answered with a failure status rather than data."""


class Dart5pctCollector(BaseCollector):
    source = "dart_5pct"

    def __init__(self, manager: dict, *, lookback_days: int = 3,
                 since: Optional[date] = None, limit: Optional[int] = None):
        super().__init__(manager)
        self.lookback_days = lookback_days
        self.since = since          # historical backfill floor; overrides lookback
        self.limit = limit          # cap issuers per run (DART daily quota)
        self._detail_type = True    # narrow the list; falls back if rejected

    def applies(self) -> bool:
        # Korean disclosures are filed under the manager's own reporter name;
        # a manager with no search terms simply has no Korean footprint here.
        return bool(config.DART_API_KEY and self.manager.get("dart_terms"))

    # ---- discover -------------------------------------------------------
    def _windows(self) -> list[tuple[date, date]]:
        """Date ranges to scan, oldest first.

        DART caps a single list.json response, so a multi-year backfill is cut
        into chunks rather than asked for at once.
        """
        end = date.today()
        start = self.since or (end - timedelta(days=self.lookback_days))
        out: list[tuple[date, date]] = []
        cursor = start
        while cursor <= end:
            stop = min(cursor + timedelta(days=_WINDOW_DAYS - 1), end)
            out.append((cursor, stop))
            cursor = stop + timedelta(days=1)
        return out

    def _list_page(self, start: date, end: date, page_no: int) -> dict:
        params = {
            "crtfc_key": config.DART_API_KEY,
            "bgn_de": start.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"),
            "page_no": str(page_no),
            "page_count": "100",
        }
        # Ask for major-holding reports specifically. 지분공시 as a whole is
        # dominated by 임원·주요주주 소유상황보고, which can push a 90-day window
        # past the page cap and silently drop issuers off the end.
        if self._detail_type:
            params["pblntf_detail_ty"] = _DETAIL_MAJOR_HOLDING
        else:
            params["pblntf_ty"] = "D"
        data = get_json(config.DART_LIST_URL, params=params)
        status = data.get("status")
        if status == "100" and self._detail_type:
            # This DART deployment does not accept the detail code; drop back to
            # the broad type rather than failing the sweep.
            print(f"[{self.log_prefix}] pblntf_detail_ty rejected; "
                  f"falling back to pblntf_ty=D")
            self._detail_type = False
            return self._list_page(start, end, page_no)
        if status == "013":            # 조회된 데이터 없음 — a real, empty answer
            return {"list": [], "total_page": 0}
        if status != "000":
            # Anything else is a failure (bad key, quota, maintenance). Returning
            # an empty list here would record the run as "ok, 0 rows", which is
            # indistinguishable from a quiet week — so fail loudly instead.
            raise DartError(
                f"DART list.json status={status} msg={data.get('message')} "
                f"({start}~{end} page {page_no})")
        return data

    def discover(self) -> list[FetchTarget]:
        if not config.DART_API_KEY:
            print("[dart_5pct] DART_API_KEY not set; skipping discovery")
            return []

        targets = self._sweep()
        if not targets and self._detail_type:
            # An empty sweep is a legitimate answer, but it is also what a wrong
            # detail code would produce — and that would be read as "this manager
            # holds nothing in Korea". Confirm against the broad type before
            # letting the emptiness stand.
            print(f"[{self.log_prefix}] nothing found with "
                  f"pblntf_detail_ty={_DETAIL_MAJOR_HOLDING}; "
                  f"re-checking with pblntf_ty=D")
            self._detail_type = False
            targets = self._sweep()
        return targets

    def _sweep(self) -> list[FetchTarget]:
        seen_corps: dict[str, FetchTarget] = {}
        scanned = 0
        stopped_early = None
        truncated: list[tuple[date, date, int]] = []
        for start, end in self._windows():
            if stopped_early:
                break
            page_no, total_pages = 1, 1
            while page_no <= min(total_pages, _MAX_PAGES):
                try:
                    data = self._list_page(start, end, page_no)
                except DartError as exc:
                    # A sweep spanning years can exhaust the daily quota partway.
                    # Throwing away thousands of issuers already found would make
                    # the run worthless; keep them and let the next run resume.
                    # With nothing found yet the failure is the whole story, so
                    # it still propagates.
                    if not seen_corps:
                        raise
                    stopped_early = exc
                    break
                total_pages = int(data.get("total_page") or 0)
                if page_no == 1 and total_pages > _MAX_PAGES:
                    truncated.append((start, end, total_pages))
                items = data.get("list") or []
                scanned += len(items)
                for it in items:
                    report_nm = it.get("report_nm") or ""
                    if not any(k in report_nm for k in _MAJOR_HOLDING_KEYWORDS):
                        continue
                    corp_code = it.get("corp_code")
                    if not corp_code or corp_code in seen_corps:
                        continue
                    seen_corps[corp_code] = FetchTarget(
                        source=self.source,
                        external_id=None,   # keyed by content hash; many rcept per corp
                        url=config.DART_MAJORSTOCK_URL + f"?corp_code={corp_code}",
                        meta={"corp_code": corp_code,
                              "stock_code": it.get("stock_code")},
                    )
                page_no += 1

        if truncated:
            worst = max(t[2] for t in truncated)
            print(f"[{self.log_prefix}] WARNING: {len(truncated)} window(s) had "
                  f"more than {_MAX_PAGES} pages (worst {worst}) — issuers past "
                  f"the cap were not seen; narrow the window to cover them")
        if stopped_early:
            print(f"[{self.log_prefix}] stopped early: {stopped_early} — "
                  f"keeping what was found; re-run to continue")
        targets = list(seen_corps.values())
        window = self._windows()
        capped = ""
        if self.limit and len(targets) > self.limit:
            capped = f" (capped to {self.limit} this run)"
            targets = targets[: self.limit]
        print(f"[{self.log_prefix}] scanned {scanned} disclosure(s) over "
              f"{window[0][0]}~{window[-1][1]}; {len(seen_corps)} issuer(s) with "
              f"a major-holding report{capped}")
        return targets

    # ---- fetch ----------------------------------------------------------
    def fetch(self, target: FetchTarget) -> Optional[RawDoc]:
        import json

        data = get_json(
            config.DART_MAJORSTOCK_URL,
            params={"crtfc_key": config.DART_API_KEY,
                    "corp_code": target.meta["corp_code"]},
        )
        if data.get("status") not in ("000", "013"):  # 013 = no data
            print(f"[dart_5pct] majorstock status={data.get('status')}")
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return RawDoc(
            source=self.source,
            external_id=None,
            url=target.url,
            payload=payload,
            content_hash=sha256_hex(payload),
            meta=target.meta,
        )

    # ---- persist --------------------------------------------------------
    def persist(self, conn, raw_id, raw_payload, target) -> int:
        rows = parse_dart_majorstock(
            raw_payload,
            search_terms=list(self.manager.get("dart_terms") or []),
            ticker=target.meta.get("stock_code"),
        )
        n = repo.insert_kr_holdings(conn, self.manager_id, rows, raw_id)
        for r in rows:
            diff.diff_kr_holdings(conn, self.manager_id, r.rcept_no, r.corp_code)
        return n

    # DART targets have no external_id; dedup happens on content_hash in run().
    def already_have_target(self, conn, target: FetchTarget) -> bool:
        return False
