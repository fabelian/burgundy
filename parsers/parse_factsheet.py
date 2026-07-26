"""Parse a fund fact sheet into positions.

Fact sheets are the only source that reaches a Korean large cap for these
managers (docs/korea-holdings.md), and they are PDFs laid out for a reader
rather than a machine.

Calibrated against the Mawer International Equity Fund (Series F) sheet as at
30 June 2026 — ``tests/fixtures/mawer_international_equity_series_f.txt`` is its
extracted text. What that document dictates:

* The holdings block is headed ``Top 25 Holdings % Weight`` and **appears twice**,
  once per printed column, then ends at a ``Total 58.7`` line.
* Entries are ``Name<space>Weight`` on one line, with no country column. Korean
  identification therefore falls to ``parsers.securities``, which is why its
  name list is load-bearing rather than a nicety.
* ``Cash and Cash Equivalents`` is listed as if it were a position, and is
  counted in the printed total.
* ``Number of Holdings: 72`` against 25 listed is what proves the list is a
  top-N extract and not the portfolio.

Two anti-silence rules run the design, because the failure that matters is not
a crash but a plausible empty answer — "this manager holds nothing Korean" is a
sentence someone acts on:

* every anchor is required; a redesigned sheet raises rather than returning [].
* the parsed weights are checked against the document's own printed total. The
  sector and region blocks higher up the same page use the identical
  ``Name 12.3`` shape, so a block picked up one heading too early still parses
  cleanly — only the sum gives it away.
"""
from __future__ import annotations

import base64
import io
import re
from datetime import date
from typing import Optional

from dateutil import parser as dateparse

from collectors.types import FundHoldingRow
from parsers.securities import security_key


class FactsheetFormatUnknown(RuntimeError):
    """The document was fetched but its layout has not been calibrated."""


def pdf_text(data: bytes) -> str:
    """Extract the text layer of a PDF, page by page.

    Pages are joined with form feeds so a later parser can still tell where one
    ended — holdings tables are usually on a single page and page boundaries
    are a useful anchor.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\f".join((page.extract_text() or "") for page in reader.pages)


def describe(data: bytes) -> dict:
    """Characterise a fetched document without interpreting it.

    This is the report that makes the next step possible: whether the PDF has a
    text layer at all decides whether the parser can be text-based or needs OCR,
    and it can only be answered against a real file.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = len(reader.pages)
    except Exception as exc:
        return {"pages": 0, "chars": 0, "has_text_layer": False,
                "error": str(exc)}
    text = pdf_text(data)
    return {
        "pages": pages,
        "chars": len(text.replace("\f", "").strip()),
        "has_text_layer": bool(text.replace("\f", "").strip()),
    }


def decode_payload(payload: str) -> bytes:
    """Recover the original PDF from a ``raw_documents.payload``.

    ``payload`` is TEXT, so a PDF is stored base64-encoded; layer 1 is meant to
    hold the untouched original and base64 is the only lossless way to put bytes
    in a text column.
    """
    return base64.b64decode(payload)


def encode_payload(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

_AS_OF = re.compile(r"As at\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")
_HOLDINGS_HEADER = re.compile(r"^Top\s+(\d+)\s+Holdings\b.*$", re.MULTILINE)
_TOTAL = re.compile(r"^Total\s+(\d+(?:\.\d+)?)\s*$")
# The footnote marker ("Number of Holdings1:") sits between the label and the
# colon, and the value is on the following line.
_HOLDING_COUNT = re.compile(r"Number of Holdings\d*:\s*(\d+)")
# A name may contain digits ("PRIO SA/Brazil"), so the weight is anchored to
# the end of the line and taken non-greedily.
_ENTRY = re.compile(r"^(?P<name>.+?)\s+(?P<weight>\d{1,3}(?:\.\d+)?)$")

# Weights are printed to one decimal, so 25 rows can drift by a little over a
# point through rounding alone. Wide enough to allow that, far too tight for a
# sector block (which sums to 100) to slip past.
_SUM_TOLERANCE_PER_ROW = 0.06
_SUM_TOLERANCE_FLOOR = 0.5


def _fail(fund, period_label, reason: str,
          payload: Optional[str] = None) -> "FactsheetFormatUnknown":
    """The message is the handover to whoever re-calibrates the parser, so it
    carries the document's shape as well as what went wrong."""
    shape = ""
    if payload is not None:
        detail = describe(decode_payload(payload))
        shape = (f" pages={detail['pages']} chars={detail['chars']}"
                 f" text_layer={detail['has_text_layer']}")
    return FactsheetFormatUnknown(
        f"{reason} (fund={(fund or {}).get('slug')} period={period_label}"
        f"{shape}); the document is stored in raw_documents — "
        f"see parsers/parse_factsheet.py"
    )


def _as_of_date(text: str) -> Optional[date]:
    match = _AS_OF.search(text)
    if not match:
        return None
    try:
        return dateparse.parse(match.group(1)).date()
    except (ValueError, OverflowError):
        return None


def _is_cash(name: str) -> bool:
    """Cash is printed as if it were a position, and it is not one."""
    return "cash" in security_key(name).split()


def _holdings_entries(text: str) -> tuple[list[tuple[str, float]], int, Optional[float]]:
    """Rows of the holdings block, the N the header claims, and its printed total.

    Scanning starts at the *first* header and runs to the total, so the repeated
    header of the second printed column is passed over rather than restarting
    the block.
    """
    header = _HOLDINGS_HEADER.search(text)
    if not header:
        return [], 0, None
    claimed_n = int(header.group(1))

    entries: list[tuple[str, float]] = []
    printed_total: Optional[float] = None
    # A long name can wrap onto its own line, leaving the weight on the next.
    # The orphan is carried forward and prepended rather than dropped, so a
    # wrapped position keeps its full name instead of being filed under its tail.
    pending = ""
    for line in text[header.end():].splitlines():
        line = line.strip()
        if not line:
            continue
        if _HOLDINGS_HEADER.match(line):     # the next printed column
            pending = ""
            continue
        total = _TOTAL.match(line)
        if total:
            printed_total = float(total.group(1))
            break
        entry = _ENTRY.match(line)
        if not entry:
            pending = f"{pending} {line}".strip()
            continue
        name = f"{pending} {entry.group('name')}".strip()
        pending = ""
        entries.append((name, float(entry.group("weight"))))
    return entries, claimed_n, printed_total


def parse_factsheet(payload: str, *, fund: Optional[dict] = None,
                    period_label: Optional[str] = None) -> list[FundHoldingRow]:
    """Positions listed by a fact sheet, from a stored ``raw_documents`` payload."""
    return parse_factsheet_text(pdf_text(decode_payload(payload)), fund=fund,
                                period_label=period_label, _payload=payload)


def parse_factsheet_text(text: str, *, fund: Optional[dict] = None,
                         period_label: Optional[str] = None,
                         _payload: Optional[str] = None) -> list[FundHoldingRow]:
    """Positions listed by a fact sheet, from its extracted text.

    Split from ``parse_factsheet`` so the layout rules can be tested against a
    checked-in text fixture instead of half a megabyte of binary.

    Raises ``FactsheetFormatUnknown`` rather than returning an empty list when
    the layout stops matching: an empty answer here reads as "this manager holds
    nothing Korean", which is a conclusion someone acts on.
    """
    payload = _payload

    as_of = _as_of_date(text)
    if as_of is None:
        raise _fail(fund, period_label,
                    "no 'As at <date>' line — cannot date the positions", payload)

    entries, claimed_n, printed_total = _holdings_entries(text)
    if not entries:
        raise _fail(fund, period_label,
                    "no 'Top N Holdings' block found", payload)

    if printed_total is None:
        raise _fail(fund, period_label,
                    "holdings block has no 'Total' line to check the parse "
                    "against", payload)
    parsed_total = sum(w for _, w in entries)
    tolerance = max(_SUM_TOLERANCE_FLOOR,
                    _SUM_TOLERANCE_PER_ROW * len(entries))
    if abs(parsed_total - printed_total) > tolerance:
        raise _fail(
            fund, period_label,
            f"parsed weights sum to {parsed_total:.1f}% but the document prints "
            f"{printed_total:.1f}% over {len(entries)} row(s) — the wrong block "
            f"was read", payload)

    # Cash counts towards the printed total, so it is checked and only then
    # dropped: it is not a position and must never rank as one.
    securities = [(name, weight) for name, weight in entries
                  if not _is_cash(name)]

    total_holdings = _HOLDING_COUNT.search(text)
    # "Number of Holdings" is the whole portfolio; the block is an extract of
    # it. Without that number the safe reading is the conservative one — a
    # top-N list wrongly called complete turns "not printed" into "not held".
    scope = ("full" if total_holdings
             and len(securities) >= int(total_holdings.group(1))
             else "top_n")

    return [
        FundHoldingRow(
            as_of_date=as_of,
            security_key=security_key(name),
            security_name=name,
            weight=weight,
            position_rank=rank,
            disclosure_scope=scope,
            positions_listed=claimed_n,
        )
        for rank, (name, weight) in enumerate(securities, start=1)
    ]
