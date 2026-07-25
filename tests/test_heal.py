from datetime import date

from collectors.types import HoldingRow
from pipeline import repo
from pipeline.reparse import heal_13f_aum


def _hold(acc, as_of, cusip, value):
    return HoldingRow(as_of, as_of, acc, False, cusip, f"N{cusip}", 10, value,
                      None, None)


def test_heal_fills_missing_13f_total(db):
    repo.insert_holdings(db, [
        _hold("A1", date(2024, 12, 31), "AAA", 150),
        _hold("A1", date(2024, 12, 31), "BBB", 50),
    ], None)
    assert db.execute("SELECT count(*) c FROM aum_history").fetchone()["c"] == 0

    healed = heal_13f_aum(db)
    assert healed == 1
    row = db.execute(
        "SELECT aum, source FROM aum_history WHERE source='13f_total'"
    ).fetchone()
    assert row["source"] == "13f_total"
    assert float(row["aum"]) == 200.0  # post-2023: whole USD, 150+50


def test_heal_is_idempotent(db):
    repo.insert_holdings(db, [_hold("A1", date(2024, 12, 31), "AAA", 150)], None)
    assert heal_13f_aum(db) == 1
    assert heal_13f_aum(db) == 0  # nothing missing on the second pass


def test_heal_pre_2023_scales_to_dollars(db):
    repo.insert_holdings(db, [_hold("A0", date(2022, 12, 31), "AAA", 100)], None)
    heal_13f_aum(db)
    row = db.execute(
        "SELECT aum FROM aum_history WHERE as_of_date='2022-12-31'"
    ).fetchone()
    assert float(row["aum"]) == 100 * 1000  # thousands -> whole USD
