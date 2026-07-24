import pathlib
from datetime import date

from parsers.parse_13f import parse_13f

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
