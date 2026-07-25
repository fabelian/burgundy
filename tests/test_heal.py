from datetime import date

from collectors.types import HoldingRow
from pipeline import repo
from pipeline.reparse import heal_13f_aum


def _hold(acc, as_of, cusip, value, filed_at=None):
    return HoldingRow(as_of, filed_at or as_of, acc, False, cusip, f"N{cusip}",
                      10, value, None, None)


def test_heal_fills_missing_13f_total(db):
    repo.insert_holdings(db, [
        _hold("A1", date(2024, 12, 31), "AAA", 150, date(2025, 2, 14)),
        _hold("A1", date(2024, 12, 31), "BBB", 50, date(2025, 2, 14)),
    ], None)
    assert db.execute("SELECT count(*) c FROM aum_history").fetchone()["c"] == 0

    assert heal_13f_aum(db) == (1, 0)
    row = db.execute(
        "SELECT aum, source FROM aum_history WHERE source='13f_total'"
    ).fetchone()
    assert row["source"] == "13f_total"
    assert float(row["aum"]) == 200.0  # filed post-2023: whole USD, 150+50


def test_heal_is_idempotent(db):
    repo.insert_holdings(db, [
        _hold("A1", date(2024, 12, 31), "AAA", 150, date(2025, 2, 14))], None)
    assert heal_13f_aum(db) == (1, 0)
    assert heal_13f_aum(db) == (0, 0)  # nothing missing, nothing to correct


def test_heal_pre_2023_scales_to_dollars(db):
    repo.insert_holdings(db, [
        _hold("A0", date(2022, 9, 30), "AAA", 100, date(2022, 11, 14))], None)
    heal_13f_aum(db)
    row = db.execute(
        "SELECT aum FROM aum_history WHERE as_of_date='2022-09-30'"
    ).fetchone()
    assert float(row["aum"]) == 100 * 1000  # thousands -> whole USD


def test_heal_q4_2022_uses_filing_date_not_period(db):
    """Q4-2022 is filed in 2023, so its values are already whole dollars."""
    repo.insert_holdings(db, [
        _hold("A0", date(2022, 12, 31), "AAA", 100, date(2023, 2, 14))], None)
    heal_13f_aum(db)
    row = db.execute(
        "SELECT aum FROM aum_history WHERE as_of_date='2022-12-31'"
    ).fetchone()
    assert float(row["aum"]) == 100  # not scaled by 1000


def test_heal_corrects_a_value_stored_under_the_wrong_rule(db):
    """A wrong value already in the table must be repaired, not skipped.

    ``insert_aum`` is ON CONFLICT DO NOTHING, so without an explicit correction
    the 1000x-scaled Q4-2022 row would survive every future run.
    """
    repo.insert_holdings(db, [
        _hold("A0", date(2022, 12, 31), "AAA", 100, date(2023, 2, 14))], None)
    db.execute(
        "INSERT INTO aum_history (as_of_date, aum, currency, source) "
        "VALUES ('2022-12-31', %s, 'USD', '13f_total')", (100 * 1000,)
    )

    assert heal_13f_aum(db) == (0, 1)
    row = db.execute(
        "SELECT aum FROM aum_history WHERE as_of_date='2022-12-31'"
    ).fetchone()
    assert float(row["aum"]) == 100

    event = db.execute(
        "SELECT before, after, change_type FROM changes "
        " WHERE change_type='AUM_CORRECTED' AND as_of_date='2022-12-31'"
    ).fetchone()
    assert event["before"]["aum"] == 100_000
    assert event["after"]["aum"] == 100

    assert heal_13f_aum(db) == (0, 0)  # settled
