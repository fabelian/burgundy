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
    assert row["positions"] == 2        # the partial amendment, not the original
    assert row["is_amendment"] is True
    assert row["filings"] == 2          # two filings exist for the quarter


def test_table_marks_the_collapse_as_suspect(db):
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
    collapsed = by_date[date(2017, 9, 30)]
    assert collapsed["suspect"] is True
    assert collapsed["aum"] < by_date[date(2017, 6, 30)]["aum"] / 100


def test_non_13f_sources_have_no_position_count(db):
    db.execute(
        "INSERT INTO aum_history (as_of_date, aum, currency, source) "
        "VALUES ('2025-06-30', 12000000000, 'CAD', 'website')"
    )
    db.commit()  # queries.* open their own connection

    row = queries.aum_table()[0]
    assert row["source"] == "website"
    assert row["positions"] is None
