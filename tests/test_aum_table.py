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


def _holdings(acc, as_of, filed, count, value_each, amendment=False,
              shares_each=1_000_000):
    # shares_each puts the implied price at ~$0.10, i.e. reported in thousands,
    # which is what the unit inference reads.
    return [HoldingRow(as_of, filed, acc, amendment, f"C{i:04d}", f"N{i}",
                       shares_each, value_each, None, None)
            for i in range(count)]


def test_table_reports_position_count_and_amendment(db, manager):
    repo.insert_holdings(db, manager, _holdings(
        "ORIG", date(2017, 9, 30), date(2017, 11, 14), 100, 105_000), None)
    repo.insert_holdings(db, manager, _holdings(
        "AMEND", date(2017, 9, 30), date(2017, 12, 1), 2, 17_647,
        amendment=True), None)
    heal_13f_aum(db, manager)
    db.commit()  # queries.* open their own connection

    row = queries.aum_table(manager)[0]
    assert row["positions"] == 100      # the full original, not the 2-row amendment
    assert row["is_amendment"] is False
    assert row["filings"] == 2          # two filings exist for the quarter


def test_partial_amendment_does_not_replace_the_quarter(db, manager):
    repo.insert_holdings(db, manager, _holdings(
        "Q2", date(2017, 6, 30), date(2017, 8, 14), 100, 105_465), None)
    repo.insert_holdings(db, manager, _holdings(
        "Q3", date(2017, 9, 30), date(2017, 11, 14), 100, 105_000), None)
    repo.insert_holdings(db, manager, _holdings(
        "Q3A", date(2017, 9, 30), date(2017, 12, 1), 2, 17_647,
        amendment=True), None)
    heal_13f_aum(db, manager)
    db.commit()  # queries.* open their own connection

    by_date = {r["as_of_date"]: r for r in queries.aum_table(manager)}
    assert by_date[date(2017, 6, 30)]["suspect"] is False
    # the partial amendment no longer stands in for the quarter
    q3 = by_date[date(2017, 9, 30)]
    assert q3["suspect"] is False
    assert q3["positions"] == 100
    assert q3["aum"] == 100 * 105_000 * 1000


def test_non_13f_sources_have_no_position_count(db, manager):
    db.execute(
        "INSERT INTO aum_history (manager_id, as_of_date, aum, currency, source) "
        "VALUES (%s, '2025-06-30', 12000000000, 'CAD', 'website')", (manager,)
    )
    db.commit()  # queries.* open their own connection

    row = queries.aum_table(manager)[0]
    assert row["source"] == "website"
    assert row["positions"] is None


def test_full_restatement_still_wins_on_recency(db, manager):
    """A real 13F-HR/A restates the whole portfolio and must replace the original.

    It can legitimately hold fewer positions than the filing it corrects — only
    a filing far below the quarter's fullest view is treated as partial.
    """
    repo.insert_holdings(db, manager, _holdings(
        "ORIG", date(2019, 3, 31), date(2019, 5, 14), 104, 100_000), None)
    repo.insert_holdings(db, manager, _holdings(
        "RESTATED", date(2019, 3, 31), date(2019, 6, 1), 98, 100_000,
        amendment=True), None)
    heal_13f_aum(db, manager)
    db.commit()

    row = queries.aum_table(manager)[0]
    assert row["positions"] == 98
    assert row["is_amendment"] is True
    assert row["aum"] == 98 * 100_000 * 1000


def test_composition_folds_the_tail_and_recomputes_weights(db, manager):
    """The pies show the largest positions plus one folded remainder.

    Weights come from the filing's own values, not the stored ``weight``, so a
    slice always sums against the portfolio actually on screen.
    """
    big = _holdings("Q1", date(2025, 3, 31), date(2025, 5, 12), 1, 500_000)
    small = _holdings("Q1", date(2025, 3, 31), date(2025, 5, 12), 14, 10_000)
    for i, r in enumerate(small):      # distinct cusips
        r.cusip = f"S{i:04d}"
    repo.insert_holdings(db, manager, big + small, None)
    db.commit()

    comp = queries.us_holdings(manager)["composition"]["current"]
    assert len(comp) == queries.TOP_N + 1          # top N plus 기타
    assert comp[-1]["label"] == "기타"
    assert comp[0]["pct"] > comp[1]["pct"]         # ordered by size
    assert round(sum(c["pct"] for c in comp)) == 100

    total = 500_000 + 14 * 10_000
    assert comp[0]["pct"] == round(100 * 500_000 / total, 2)


def test_composition_has_no_tail_slice_when_everything_fits(db, manager):
    rows = _holdings("Q1", date(2025, 3, 31), date(2025, 5, 12), 3, 10_000)
    for i, r in enumerate(rows):
        r.cusip = f"F{i:04d}"
    repo.insert_holdings(db, manager, rows, None)
    db.commit()

    comp = queries.us_holdings(manager)["composition"]["current"]
    assert len(comp) == 3
    assert all(c["label"] != "기타" for c in comp)


def test_composition_is_empty_without_a_prior_quarter(db, manager):
    rows = _holdings("Q1", date(2025, 3, 31), date(2025, 5, 12), 2, 10_000)
    rows[1].cusip = "OTHER"
    repo.insert_holdings(db, manager, rows, None)
    db.commit()

    data = queries.us_holdings(manager)
    assert data["composition"]["current"]
    assert data["composition"]["previous"] == []
