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
class FundHoldingRow:
    """One position printed by a fund's own disclosure document.

    ``security_key`` is derived from the printed name (parsers.securities) —
    fact sheets carry no CUSIP — and is what makes a re-fetch idempotent.

    ``disclosure_scope`` records whether the document listed the whole portfolio
    or only its largest positions. A row from a ``top_n`` document says nothing
    about what the fund does *not* hold.

    ``is_korean`` is classified here rather than by each parser, so no future
    fact-sheet format can put a Samsung position in the database that the Korea
    tab then fails to show. Pass it explicitly only to override the default
    classification.
    """
    as_of_date: date
    security_key: str
    security_name: str
    ticker: Optional[str] = None
    isin: Optional[str] = None
    country: Optional[str] = None
    weight: Optional[float] = None
    market_value: Optional[float] = None
    currency: Optional[str] = None
    position_rank: Optional[int] = None
    disclosure_scope: str = "top_n"
    positions_listed: Optional[int] = None
    published_at: Optional[date] = None
    is_korean: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.is_korean is None:
            from parsers.securities import is_korean

            self.is_korean = is_korean(
                country=self.country, name=self.security_name,
                ticker=self.ticker, isin=self.isin,
            )


@dataclass
class FundSnapshotRow:
    """What a fund document says about the fund, as opposed to its positions.

    ``nav`` is the whole fund's net assets in absolute units. It is what turns
    a weight into a number anyone can act on: 3% is only meaningful against the
    fund it is 3% of.
    """
    as_of_date: date
    nav: Optional[float] = None
    nav_currency: Optional[str] = None
    total_holdings: Optional[int] = None


@dataclass
class FactsheetDoc:
    """A parsed fund document: the fund-level facts plus its positions."""
    snapshot: FundSnapshotRow
    holdings: list = field(default_factory=list)


@dataclass
class ProxyVoteRow:
    """One meeting a fund voted at — evidence that it held the issuer.

    Carries no weight, and that absence is the information: a voting record has
    no top-N ceiling, so it reaches positions a fact sheet cannot show, but it
    never says how large they are.

    ``is_korean`` is classified here for the same reason it is on
    ``FundHoldingRow`` — the Korea tab must not depend on a parser remembering.
    """
    period_ended: date
    meeting_date: date
    security_key: str
    issuer_name: str
    ticker: Optional[str] = None
    country: Optional[str] = None
    ballots: Optional[int] = None
    is_korean: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.is_korean is None:
            from parsers.securities import is_korean

            self.is_korean = is_korean(
                country=self.country, name=self.issuer_name, ticker=self.ticker,
            )


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
