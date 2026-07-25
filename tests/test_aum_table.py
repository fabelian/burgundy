"""The AUM table has to carry enough evidence to judge a number.

A quarter's 13f_total comes from one filing — the latest, amendment preferred.
When that filing is a partial 13F-HR/A restating only a couple of positions,
the total collapses, and nothing in the amount itself says why. The position
count and amendment flag are what make that diagnosable.
"""
from datetime import date

from collectors.types import HoldingRow
from dashboard import queries
from pipeline import repo
from pipeline.reparse import heal_13f_aum


def _holdings(acc, as_of, filed, count, value_each, amendment=False):
    return [HoldingRow(as_of, filed, acc, amendment, f"C{i:04d}", f"N{i}", 10,
                       value_each, None, None)
            for i in range(count)]


def test_table_reports_position_count_and_amendment(db):
    repo.insert_holdings(db, _holdings(
        "ORIG", date(2017, 9, 30), date(2017, 11, 14), 100, 105_000), None)
    repo.insert_holdings(db, _holdings(
        "AMEND", date(2017, 9, 30), date(2017, 12, 1), 2, 17_647,
        amendment=True), None)
    heal_13f_aum(db)
    db.commit()  # queries.* open their own connection

    row = queries.aum_table()[0]
    assert row["positions"] == 100      # the full original, not the 2-row amendment
    assert row["is_amendment"] is False
    assert row["filings"] == 2          # two filings exist for the quarter


def test_partial_amendment_does_not_replace_the_quarter(db):
    repo.insert_holdings(db, _holdings(
        "Q2", date(2017, 6, 30), date(2017, 8, 14), 100, 105_465), None)
    repo.insert_holdings(db, _holdings(
        "Q3", date(2017, 9, 30), date(2017, 11, 14), 100, 105_000), None)
    repo.insert_holdings(db, _holdings(
        "Q3A", date(2017, 9, 30), date(2017, 12, 1), 2, 17_647,
        amendment=True), None)
    heal_13f_aum(db)
    db.commit()  # queries.* open their own connection

    by_date = {r["as_of_date"]: r for r in queries.aum_table()}
    assert by_date[date(2017, 6, 30)]["suspect"] is False
    # the partial amendment no longer stands in for the quarter
    q3 = by_date[date(2017, 9, 30)]
    assert q3["suspect"] is False
    assert q3["positions"] == 100
    assert q3["aum"] == 100 * 105_000 * 1000


def test_non_13f_sources_have_no_position_count(db):
    db.execute(
        "INSERT INTO aum_history (as_of_date, aum, currency, source) "
        "VALUES ('2025-06-30', 12000000000, 'CAD', 'website')"
    )
    db.commit()  # queries.* open their own connection

    row = queries.aum_table()[0]
    assert row["source"] == "website"
    assert row["positions"] is None


def test_full_restatement_still_wins_on_recency(db):
    """A real 13F-HR/A restates the whole portfolio and must replace the original.

    It can legitimately hold fewer positions than the filing it corrects — only
    a filing far below the quarter's fullest view is treated as partial.
    """
    repo.insert_holdings(db, _holdings(
        "ORIG", date(2019, 3, 31), date(2019, 5, 14), 104, 100_000), None)
    repo.insert_holdings(db, _holdings(
        "RESTATED", date(2019, 3, 31), date(2019, 6, 1), 98, 100_000,
        amendment=True), None)
    heal_13f_aum(db)
    db.commit()

    row = queries.aum_table()[0]
    assert row["positions"] == 98
    assert row["is_amendment"] is True
    assert row["aum"] == 98 * 100_000 * 1000
