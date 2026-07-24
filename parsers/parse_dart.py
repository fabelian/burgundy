"""Parse DART 대량보유상황보고 (majorstock.json) payloads.

Pure function: raw JSON payload -> list[KrHoldingRow].

The majorstock API returns every 5%-holder report for one issuer. We keep only
rows whose reporter (``repror``) matches the configured search terms, so the
result is Burgundy's stakes in that issuer.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from dateutil import parser as dateparse

import config
from collectors.types import KrHoldingRow


def _to_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    s = s.strip().replace(".", "-").replace("/", "-")
    try:
        return dateparse.parse(s).date()
    except (ValueError, OverflowError):
        return None


def _to_int(s: Optional[str]) -> Optional[int]:
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _to_pct(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    s = str(s).replace(",", "").replace("%", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _reporter_matches(reporter: str, terms: list[str]) -> bool:
    if not reporter:
        return False
    low = reporter.lower()
    return any(t.lower() in low for t in terms)


def parse_dart_majorstock(
    payload: str,
    *,
    search_terms: Optional[list[str]] = None,
    ticker: Optional[str] = None,
) -> list[KrHoldingRow]:
    """Parse a majorstock.json payload into KrHoldingRow list.

    When ``search_terms`` is given, only rows whose reporter matches are kept.
    """
    terms = search_terms if search_terms is not None else config.DART_SEARCH_TERMS
    data = json.loads(payload) if isinstance(payload, str) else payload
    items = data.get("list", []) if isinstance(data, dict) else []

    rows: list[KrHoldingRow] = []
    for it in items:
        reporter = it.get("repror") or ""
        if terms and not _reporter_matches(reporter, terms):
            continue
        rcept_no = it.get("rcept_no")
        corp_code = it.get("corp_code")
        if not rcept_no or not corp_code:
            continue
        rcept_dt = _to_date(it.get("rcept_dt")) or date.today()
        rows.append(
            KrHoldingRow(
                as_of_date=rcept_dt,
                filed_at=rcept_dt,
                rcept_no=str(rcept_no),
                corp_code=str(corp_code),
                corp_name=it.get("corp_name") or "",
                ticker=ticker or it.get("stock_code"),
                shares=_to_int(it.get("stkqy")),
                ownership_pct=_to_pct(it.get("stkrt")),
                report_type=it.get("report_tp") or it.get("report_resn"),
            )
        )
    return rows
