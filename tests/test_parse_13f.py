import pathlib
from datetime import date

from parsers.parse_13f import compute_total_aum, parse_13f

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _load():
    xml = (FIXTURES / "sample_13f.xml").read_text(encoding="utf-8")
    return parse_13f(
        xml,
        as_of_date=date(2024, 3, 31),
        filed_at=date(2024, 5, 15),
        accession_no="0001234567-24-000001",
        is_amendment=False,
    )


def test_row_count():
    rows = _load()
    assert len(rows) == 2


def test_values_and_shares():
    rows = _load()
    by_cusip = {r.cusip: r for r in rows}
    aapl = by_cusip["037833100"]
    assert aapl.name == "APPLE INC"
    assert aapl.shares == 1_000_000
    assert aapl.value_kusd == 150_000
    msft = by_cusip["594918104"]
    assert msft.shares == 200_000
    assert msft.value_kusd == 50_000


def test_weights_sum_to_one():
    rows = _load()
    total = sum(r.weight for r in rows)
    assert abs(total - 1.0) < 1e-6
    by_cusip = {r.cusip: r for r in rows}
    # Apple is 150k of 200k total = 0.75
    assert abs(by_cusip["037833100"].weight - 0.75) < 1e-6


def test_metadata_propagated():
    rows = _load()
    for r in rows:
        assert r.as_of_date == date(2024, 3, 31)
        assert r.filed_at == date(2024, 5, 15)
        assert r.accession_no == "0001234567-24-000001"
        assert r.is_amendment is False


def test_the_filings_own_unit_beats_the_filing_date():
    """The fixture implies ~$0.15/share, i.e. thousands, despite a 2024 filing.

    Filers moved to whole dollars at different times, so what the filing itself
    says outranks when it was filed.
    """
    rows = _load()  # total reported value = 150000 + 50000 = 200000
    aum = compute_total_aum(rows, date(2024, 3, 31), date(2024, 5, 15))
    assert aum.source == "13f_total"
    assert aum.currency == "USD"
    assert aum.aum == 200_000 * 1000


def test_total_aum_pre_2023_thousands_scaled():
    rows = _load()
    aum = compute_total_aum(rows, date(2022, 9, 30), date(2022, 11, 14))
    assert aum.aum == 200_000 * 1000  # thousands -> whole USD


def _rows(count, value_each, shares_each):
    from collectors.types import HoldingRow
    return [HoldingRow(date(2017, 6, 30), date(2017, 8, 11), "ACC", False,
                       f"C{i:04d}", f"N{i}", shares_each, value_each, None, None)
            for i in range(count)]


def test_unit_read_from_filing_not_calendar_when_filer_moved_early():
    """A 2017 filing already in whole dollars must not be scaled.

    EdgePoint reported whole dollars years before the SEC's change; scaling it
    by the calendar produced a 1000x spike that flattened the whole chart.
    """
    # implied price ~= $105/share -> already whole dollars
    rows = _rows(40, value_each=105_000_000, shares_each=1_000_000)
    aum = compute_total_aum(rows, date(2017, 6, 30), date(2017, 8, 11))
    assert aum.aum == 40 * 105_000_000


def test_unit_read_from_filing_when_filer_kept_thousands_after_2023():
    """A 2023+ filing still in thousands must still be scaled.

    Beutel Goodman kept USD-thousands well past the change; trusting the
    calendar dropped its whole series by 1000x.
    """
    # implied price ~= $0.055 in reported units -> thousands
    rows = _rows(70, value_each=55_000, shares_each=1_000_000)
    aum = compute_total_aum(rows, date(2022, 12, 31), date(2023, 2, 14))
    assert aum.aum == 70 * 55_000 * 1000


def test_unit_falls_back_to_the_date_without_share_counts():
    from collectors.types import HoldingRow
    rows = [HoldingRow(date(2022, 9, 30), date(2022, 11, 14), "ACC", False,
                       "C1", "N", 0, 100, None, None)]
    assert compute_total_aum(rows, date(2022, 9, 30),
                             date(2022, 11, 14)).aum == 100 * 1000
    assert compute_total_aum(rows, date(2023, 3, 31),
                             date(2023, 5, 15)).aum == 100


def test_q4_2022_filed_in_2023_scales_when_the_filing_still_uses_thousands():
    """Q4-2022 is the quarter where period and filing date disagree.

    Neither date settles it: this filing reports thousands, so it scales even
    though it was filed after the SEC's change.
    """
    rows = _load()
    aum = compute_total_aum(rows, date(2022, 12, 31), date(2023, 2, 14))
    assert aum.aum == 200_000 * 1000


def test_total_aum_empty():
    assert compute_total_aum([], date(2024, 3, 31), date(2024, 5, 15)) is None
