"""Shared dataclasses passed between collectors, parsers and the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class FetchTarget:
    """A document discovered by a collector that may need fetching."""
    source: str
    external_id: Optional[str]   # accession_no / rcept_no / None
    url: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawDoc:
    """A fetched document ready to be persisted into raw_documents."""
    source: str
    external_id: Optional[str]
    url: str
    payload: str
    content_hash: str
    meta: dict[str, Any] = field(default_factory=dict)


# ---- Snapshot rows -------------------------------------------------------

@dataclass
class HoldingRow:
    as_of_date: date
    filed_at: date
    accession_no: str
    is_amendment: bool
    cusip: str
    name: str
    shares: int
    value_kusd: int
    ticker: Optional[str] = None
    weight: Optional[float] = None


@dataclass
class KrHoldingRow:
    as_of_date: date
    filed_at: date
    rcept_no: str
    corp_code: str
    corp_name: str
    ticker: Optional[str] = None
    shares: Optional[int] = None
    ownership_pct: Optional[float] = None
    report_type: Optional[str] = None


@dataclass
class AumRow:
    as_of_date: date
    aum: float
    currency: str
    source: str


@dataclass
class PersonnelRow:
    person_name: str
    title: str
    source: str
    valid_from: date
