"""The fact-sheet collector, and its deliberate refusal to guess a layout.

The parser is uncalibrated on purpose: no real document has been read from the
development sandbox, and a parser written against an imagined layout is how the
DART sweep produced a Korea tab full of the wrong companies. What these tests
pin is that the refusal is *safe* — the document still gets fetched and kept,
because that stored document is what calibration needs.
"""
from __future__ import annotations

import io
from datetime import date

import pytest

from collectors.factsheet import (
    FactsheetCollector,
    expand_template,
    recent_periods,
)
from parsers.parse_factsheet import (
    FactsheetFormatUnknown,
    decode_payload,
    describe,
    encode_payload,
    parse_factsheet,
    pdf_text,
)


def _blank_pdf(pages: int = 1) -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


FUND = {"id": 1, "slug": "international-equity", "cadence": "quarterly",
        "doc_url_template": ("https://example.com/funds/"
                             "{q}q{yy}-international-equity.pdf")}


# ---- period expansion ----------------------------------------------------

def test_quarterly_periods_are_newest_first_and_snap_to_quarter_end():
    periods = recent_periods("quarterly", date(2024, 8, 14), count=3)
    assert [p["label"] for p in periods] == ["2024Q3", "2024Q2", "2024Q1"]
    assert [p["as_of"] for p in periods] == [
        date(2024, 9, 30), date(2024, 6, 30), date(2024, 3, 31)]


def test_quarterly_periods_cross_the_year_boundary():
    periods = recent_periods("quarterly", date(2025, 1, 5), count=2)
    assert [p["label"] for p in periods] == ["2025Q1", "2024Q4"]
    assert periods[1]["as_of"] == date(2024, 12, 31)


def test_monthly_periods_step_by_month():
    periods = recent_periods("monthly", date(2025, 2, 10), count=3)
    assert [p["label"] for p in periods] == ["2025-02", "2025-01", "2024-12"]
    assert periods[0]["as_of"] == date(2025, 2, 28)


def test_the_url_template_expands_to_the_documented_mawer_form():
    """The one path confirmed in docs/korea-holdings.md is 2q24 — the template
    has to reproduce it exactly, or every fetch 404s and reads as 'no
    disclosures'."""
    import config

    mawer = next(f for f in config.FUNDS
                 if f["manager_slug"] == "mawer"
                 and f["slug"] == "international-equity")
    period = next(p for p in recent_periods("quarterly", date(2024, 8, 1), 4)
                  if p["label"] == "2024Q2")
    url = expand_template(mawer["doc_url_template"], period)
    assert url.endswith("2q24-mawer-international-equity-fund-series-a.pdf")


def test_expansion_supports_the_documented_placeholders():
    period = next(p for p in recent_periods("quarterly", date(2024, 8, 1), 4)
                  if p["label"] == "2024Q2")
    assert expand_template("{yyyy}-{mm}-q{q}-{yy}", period) == "2024-06-q2-24"


# ---- payload round-trip --------------------------------------------------

def test_a_pdf_survives_the_text_column_unchanged():
    """raw_documents.payload is TEXT; layer 1 is meant to keep the original
    bytes, so the encoding has to be lossless."""
    pdf = _blank_pdf()
    assert decode_payload(encode_payload(pdf)) == pdf


def test_describe_reports_what_calibration_needs_to_know():
    detail = describe(_blank_pdf(pages=2))
    assert detail["pages"] == 2
    # A blank page has no text layer — which is exactly the finding that would
    # decide a real sheet needs OCR rather than text parsing.
    assert detail["has_text_layer"] is False


def test_describe_survives_a_document_that_is_not_a_pdf():
    detail = describe(b"this is not a pdf")
    assert detail["pages"] == 0 and detail["has_text_layer"] is False


def test_pdf_text_separates_pages():
    assert pdf_text(_blank_pdf(pages=3)).count("\f") == 2


# ---- the refusal ---------------------------------------------------------

def test_parsing_refuses_rather_than_inventing_holdings():
    with pytest.raises(FactsheetFormatUnknown):
        parse_factsheet(encode_payload(_blank_pdf()), fund=FUND,
                        period_label="2024Q2")


def test_the_refusal_says_which_document_and_what_it_looks_like():
    """The message is the handover to whoever calibrates the parser."""
    with pytest.raises(FactsheetFormatUnknown) as exc:
        parse_factsheet(encode_payload(_blank_pdf()), fund=FUND,
                        period_label="2024Q2")
    message = str(exc.value)
    assert "international-equity" in message and "2024Q2" in message
    assert "pages=1" in message and "raw_documents" in message


def test_persist_keeps_the_document_instead_of_failing_the_fetch(db, manager):
    """The whole point of running an uncalibrated collector: an exception here
    would roll the transaction back and throw away the very document needed to
    write the parser."""
    collector = FactsheetCollector({"id": manager, "slug": "mawer"})
    target = type("T", (), {"meta": {"fund": FUND,
                                     "period": {"label": "2024Q2"}}})()

    rows = collector.persist(db, None, encode_payload(_blank_pdf()), target)

    assert rows == 0, "nothing was parsed, so nothing may be reported as parsed"


def test_persist_stores_parsed_rows_once_a_parser_exists(db, manager,
                                                         monkeypatch):
    """The seam the calibrated parser plugs into."""
    from collectors.types import FundHoldingRow
    from parsers.securities import security_key

    db.execute(
        "INSERT INTO funds (manager_id, slug, name, mandate)"
        " VALUES (%s, 'international-equity', 'F', 'international')",
        (manager,),
    )
    fund_id = db.execute("SELECT id FROM funds").fetchone()["id"]

    monkeypatch.setattr("collectors.factsheet.parse_factsheet",
                        lambda *a, **kw: [FundHoldingRow(
                            as_of_date=date(2024, 6, 30),
                            security_key=security_key("Samsung Electronics"),
                            security_name="Samsung Electronics", weight=1.7)])
    collector = FactsheetCollector({"id": manager, "slug": "mawer"})
    target = type("T", (), {"meta": {"fund": {"id": fund_id,
                                              "slug": "international-equity"},
                                     "period": {"label": "2024Q2"}}})()

    assert collector.persist(db, None, "ignored", target) == 1
    row = db.execute("SELECT security_name, is_korean FROM fund_holdings"
                     ).fetchone()
    assert row["security_name"] == "Samsung Electronics"
    assert row["is_korean"] is True


# ---- discovery -----------------------------------------------------------

def test_discovery_covers_every_fund_period_pair(monkeypatch):
    collector = FactsheetCollector({"id": 1, "slug": "mawer"})
    monkeypatch.setattr(FactsheetCollector, "_funds", lambda self: [FUND])

    targets = collector.discover()

    assert len({t.external_id for t in targets}) == len(targets), (
        "each fund-period needs a distinct idempotency key, or later periods "
        "are skipped as already fetched")
    assert all(t.external_id.startswith("international-equity:")
               for t in targets)


def test_a_manager_with_no_tracked_fund_is_skipped(monkeypatch):
    collector = FactsheetCollector({"id": 1, "slug": "burgundy"})
    monkeypatch.setattr(FactsheetCollector, "_funds", lambda self: [])
    assert collector.applies() is False


def test_a_fund_without_a_document_url_is_not_fetched(db, manager, monkeypatch):
    """A guessed URL 404s on every run and reads as 'this manager discloses
    nothing', so a fund with no confirmed path is left out entirely."""
    import contextlib

    db.execute(
        "INSERT INTO funds (manager_id, slug, name, mandate, doc_url_template)"
        " VALUES (%s, 'no-url', 'No URL', 'global', NULL)",
        (manager,),
    )
    monkeypatch.setattr("collectors.factsheet.connect",
                        lambda: contextlib.nullcontext(db))
    collector = FactsheetCollector({"id": manager, "slug": "mawer"})
    assert collector._funds() == []
