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

import pathlib

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
    parse_factsheet_text,
    pdf_text,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _mawer_text() -> str:
    """Text of the Mawer International Equity (Series F) sheet, 30 June 2026 —
    the document this parser was calibrated against."""
    return (FIXTURES / "mawer_international_equity_series_f.txt").read_text(
        encoding="utf-8")


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


# ---- the real document ---------------------------------------------------

def test_the_holdings_block_is_read_not_the_sector_block_above_it():
    """Sector and region weights sit higher on the same page in the identical
    'Name 12.3' shape. Anchoring one heading too early parses cleanly and
    silently reports a portfolio of sectors."""
    rows = parse_factsheet_text(_mawer_text(), fund=FUND)
    names = [r.security_name for r in rows]

    assert "Taiwan Semiconductor Manufacturing Co Ltd" in names
    for sector_or_region in ("Financials", "Information Technology",
                             "Asia Pacific Ex. Japan", "United Kingdom",
                             "Emerging and Frontier Markets"):
        assert sector_or_region not in names, sector_or_region


def test_both_printed_columns_are_read():
    """The header repeats for the second column; restarting the block there
    would silently drop the first twelve positions."""
    rows = parse_factsheet_text(_mawer_text(), fund=FUND)
    names = [r.security_name for r in rows]

    assert names[0] == "Taiwan Semiconductor Manufacturing Co Ltd"  # column 1
    assert "Diploma PLC" in names                                   # column 2
    assert len(rows) == 24


def test_the_as_of_date_comes_from_the_document():
    rows = parse_factsheet_text(_mawer_text(), fund=FUND)
    assert {r.as_of_date for r in rows} == {date(2026, 6, 30)}


def test_cash_is_not_a_position():
    """It is printed inside the list and counted in the total, but ranking it
    as a holding would put 'Cash and Cash Equivalents' fourth in the fund."""
    rows = parse_factsheet_text(_mawer_text(), fund=FUND)
    assert not any("Cash" in r.security_name for r in rows)
    # ...and dropping it must not leave a hole in the ranking
    assert [r.position_rank for r in rows] == list(range(1, 25))


def test_a_top_25_extract_of_72_holdings_is_not_called_complete():
    """'Number of Holdings: 72' against 25 listed is what proves the list is an
    extract — and the tab depends on that to stop reading an unprinted position
    as an absent one."""
    rows = parse_factsheet_text(_mawer_text(), fund=FUND)
    assert {r.disclosure_scope for r in rows} == {"top_n"}
    assert {r.positions_listed for r in rows} == {25}


def test_the_korean_positions_are_found_without_a_country_column():
    """The sheet has no per-security country, so identification falls entirely
    to the name rules — this is the case the whole tab rests on."""
    rows = parse_factsheet_text(_mawer_text(), fund=FUND)
    korean = {r.security_name: r.weight for r in rows if r.is_korean}

    assert korean == {"SK hynix Inc": 3.0, "Samsung Electronics Co Ltd": 2.8}


def test_no_foreign_holding_is_claimed_as_korean():
    """The commercial failure is a false positive: another country's company
    presented to a prospect as a Korean holding."""
    rows = parse_factsheet_text(_mawer_text(), fund=FUND)
    wrongly_korean = [r.security_name for r in rows if r.is_korean
                      and r.security_name not in ("SK hynix Inc",
                                                  "Samsung Electronics Co Ltd")]
    assert wrongly_korean == []


def test_lowercased_printing_still_matches_the_name_rules():
    """The sheet prints 'SK hynix Inc', not 'SK Hynix Inc'."""
    rows = parse_factsheet_text(_mawer_text(), fund=FUND)
    hynix = next(r for r in rows if r.security_name == "SK hynix Inc")
    assert hynix.is_korean is True
    assert hynix.security_key == "sk hynix"


# ---- the anti-silence rules ----------------------------------------------

def test_a_block_that_does_not_sum_to_the_printed_total_is_rejected():
    """A dropped or spurious row still parses cleanly; only the document's own
    total gives it away."""
    text = _mawer_text().replace("Tencent Holdings Ltd 3.2\n", "")
    with pytest.raises(FactsheetFormatUnknown, match="sum to"):
        parse_factsheet_text(text, fund=FUND)


def test_a_holdings_block_with_no_total_is_rejected():
    """Without the printed total there is nothing to check the parse against,
    and an unchecked parse is what fills a tab with the wrong rows."""
    text = _mawer_text().replace("Total 58.7", "")
    with pytest.raises(FactsheetFormatUnknown, match="Total"):
        parse_factsheet_text(text, fund=FUND)


def test_a_sheet_without_an_as_of_date_is_rejected():
    text = _mawer_text().replace("As at June 30, 2026", "")
    with pytest.raises(FactsheetFormatUnknown, match="As at"):
        parse_factsheet_text(text, fund=FUND)


def test_a_redesigned_sheet_raises_instead_of_returning_nothing():
    """An empty list would reach the Korea tab as 'holds nothing Korean'."""
    with pytest.raises(FactsheetFormatUnknown, match="Top N Holdings"):
        parse_factsheet_text("As at June 30, 2026\nsome new layout\n", fund=FUND)


def test_a_wrapped_name_keeps_its_first_line():
    """A long name can break across lines, leaving the weight on the second.
    Filing the position under its tail would hide it from the name rules."""
    text = _mawer_text().replace(
        "Samsung Electronics Co Ltd 2.8",
        "Samsung Electronics\nCo Ltd 2.8")
    rows = parse_factsheet_text(text, fund=FUND)
    assert any(r.security_name == "Samsung Electronics Co Ltd" and r.is_korean
               for r in rows)


def test_parsing_refuses_when_it_cannot_read_the_document_at_all():
    with pytest.raises(FactsheetFormatUnknown):
        parse_factsheet(encode_payload(_blank_pdf()), fund=FUND,
                        period_label="2024Q2")


def test_the_refusal_says_which_document_and_what_it_looks_like():
    """The message is the handover to whoever re-calibrates the parser."""
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


# ---- the two URL shapes --------------------------------------------------

LATEST_ONLY_FUND = {"id": 2, "slug": "intl-cdn", "cadence": "quarterly",
                    "doc_url_template": None,
                    "doc_url": "https://cdn.example.com/assets/Intl_Equity.pdf"}


def test_a_latest_only_url_is_never_marked_as_seen(monkeypatch):
    """Mawer's CDN asset has no period in its path — the contents are replaced
    each quarter. Keyed by an external_id, the first fetch would mark it seen
    and every later quarter would be skipped forever; with none, dedup falls to
    the content hash and a new edition is picked up."""
    collector = FactsheetCollector({"id": 1, "slug": "mawer"})
    monkeypatch.setattr(FactsheetCollector, "_funds",
                        lambda self: [LATEST_ONLY_FUND])

    targets = collector.discover()

    assert len(targets) == 1
    assert targets[0].external_id is None
    assert targets[0].meta["period"] is None


def test_a_fund_offering_both_shapes_yields_both(monkeypatch):
    """The template reaches past quarters, the fixed URL the current one;
    neither alone gives a trend ending at today."""
    both = {**FUND, "doc_url": "https://cdn.example.com/assets/Intl_Equity.pdf"}
    collector = FactsheetCollector({"id": 1, "slug": "mawer"})
    monkeypatch.setattr(FactsheetCollector, "_funds", lambda self: [both])

    targets = collector.discover()

    assert sum(1 for t in targets if t.external_id is None) == 1
    assert sum(1 for t in targets if t.external_id is not None) > 1


def test_a_latest_only_document_is_not_labelled_with_a_guessed_quarter(db,
                                                                       manager):
    """Its as-of date comes from inside the document; inferring one from
    today's date would file the sheet under a quarter it does not cover."""
    collector = FactsheetCollector({"id": manager, "slug": "mawer"})
    target = type("T", (), {"meta": {"fund": LATEST_ONLY_FUND,
                                     "period": None}})()

    with pytest.raises(FactsheetFormatUnknown) as exc:
        parse_factsheet(encode_payload(_blank_pdf()), fund=LATEST_ONLY_FUND,
                        period_label="latest")
    assert "period=latest" in str(exc.value)
    assert collector.persist(db, None, encode_payload(_blank_pdf()),
                             target) == 0


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
