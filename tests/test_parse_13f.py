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


def test_total_aum_post_2023_whole_dollars():
    rows = _load()  # total reported value = 150000 + 50000 = 200000
    aum = compute_total_aum(rows, date(2024, 3, 31), date(2024, 5, 15))
    assert aum.source == "13f_total"
    assert aum.currency == "USD"
    assert aum.aum == 200_000        # already whole USD post-2023


def test_total_aum_pre_2023_thousands_scaled():
    rows = _load()
    aum = compute_total_aum(rows, date(2022, 9, 30), date(2022, 11, 14))
    assert aum.aum == 200_000 * 1000  # thousands -> whole USD


def test_total_aum_q4_2022_filed_in_2023_is_not_scaled():
    """The unit follows the filing date, not the period.

    Q4-2022 covers a pre-change period but is filed in early 2023, so it already
    reports whole dollars. Scaling it produced the 1000x spike that flattened
    every other quarter in the AUM chart.
    """
    rows = _load()
    aum = compute_total_aum(rows, date(2022, 12, 31), date(2023, 2, 14))
    assert aum.aum == 200_000


def test_total_aum_empty():
    assert compute_total_aum([], date(2024, 3, 31), date(2024, 5, 15)) is None
