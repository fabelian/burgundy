"""Parse a fund fact sheet into positions.

Fact sheets are the only source that reaches a Korean large cap for these
managers (docs/korea-holdings.md), and they are PDFs laid out for a reader
rather than a machine. Two halves live here:

* ``pdf_text`` / ``describe`` — format-independent. Any PDF can be turned into
  text and characterised without knowing whose it is.
* ``parse_factsheet`` — reads the holdings table. **Not calibrated.** No real
  fact sheet has been observed from this repo yet, so it raises rather than
  guessing at a layout.

The refusal is deliberate. A parser written against an imagined layout is how
the DART sweep went wrong: it ran clean, filled the Korea tab, and every row in
it was the wrong kind of company. A collector that fetches the document and
declines to interpret it leaves the original in ``raw_documents``, which is
exactly what calibrating this function needs.
"""
from __future__ import annotations

import base64
import io
from typing import Optional

from collectors.types import FundHoldingRow


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


def parse_factsheet(payload: str, *, fund: Optional[dict] = None,
                    period_label: Optional[str] = None) -> list[FundHoldingRow]:
    """Positions listed by a fact sheet. **Pending calibration.**

    To implement this, a real document is needed — one file is enough. With
    ``raw_documents`` holding it, ``describe`` and ``pdf_text`` say what the
    layout is, and this function then needs to return, per printed position:
    name, weight, country (if the sheet has the column), the sheet's stated
    as-of date, and whether the list is the whole portfolio or only the top N —
    the last one being what stops the dashboard from reading an unprinted
    position as an absent one.
    """
    detail = describe(decode_payload(payload))
    raise FactsheetFormatUnknown(
        f"fact-sheet layout not calibrated "
        f"(fund={(fund or {}).get('slug')} period={period_label} "
        f"pages={detail['pages']} chars={detail['chars']} "
        f"text_layer={detail['has_text_layer']}); "
        f"the document is stored in raw_documents — see parsers/parse_factsheet.py"
    )
