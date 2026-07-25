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


class Dart5pctCollector(BaseCollector):
    source = "dart_5pct"

    def __init__(self, manager: dict, *, lookback_days: int = 3):
        super().__init__(manager)
        self.lookback_days = lookback_days

    def applies(self) -> bool:
        # Korean disclosures are filed under the manager's own reporter name;
        # a manager with no search terms simply has no Korean footprint here.
        return bool(config.DART_API_KEY and self.manager.get("dart_terms"))

    # ---- discover -------------------------------------------------------
    def discover(self) -> list[FetchTarget]:
        if not config.DART_API_KEY:
            print("[dart_5pct] DART_API_KEY not set; skipping discovery")
            return []
        end = date.today()
        start = end - timedelta(days=self.lookback_days)
        params = {
            "crtfc_key": config.DART_API_KEY,
            "bgn_de": start.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"),
            "pblntf_ty": "D",          # 지분공시
            "page_count": "100",
        }
        data = get_json(config.DART_LIST_URL, params=params)
        if data.get("status") != "000":
            print(f"[dart_5pct] list.json status={data.get('status')} "
                  f"msg={data.get('message')}")
            return []

        seen_corps: dict[str, FetchTarget] = {}
        for it in data.get("list", []):
            report_nm = it.get("report_nm") or ""
            if not any(k in report_nm for k in _MAJOR_HOLDING_KEYWORDS):
                continue
            corp_code = it.get("corp_code")
            if not corp_code or corp_code in seen_corps:
                continue
            seen_corps[corp_code] = FetchTarget(
                source=self.source,
                external_id=None,       # keyed by content hash; many rcept per corp
                url=config.DART_MAJORSTOCK_URL + f"?corp_code={corp_code}",
                meta={"corp_code": corp_code,
                      "stock_code": it.get("stock_code")},
            )
        return list(seen_corps.values())

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
