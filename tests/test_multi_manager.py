"""Two managers must not be able to see or overwrite each other's data.

The pre-003 schema keyed aum_history on (as_of_date, source) alone, so a second
manager's 13f_total for a quarter would have silently collided with the first
one's — one firm's AUM appearing under another's name, with nothing to show for
it. These tests pin the isolation that fixed it.
"""
from datetime import date

from collectors.types import HoldingRow
from dashboard import queries
from pipeline import managers, repo
from pipeline.reparse import heal_13f_aum


def _hold(acc, as_of, cusip, value, filed_at=None):
    return HoldingRow(as_of, filed_at or as_of, acc, False, cusip, f"N{cusip}",
                      10, value, None, None)


def test_same_quarter_aum_does_not_collide(db, manager, other_manager):
    repo.insert_holdings(db, manager, [
        _hold("A-1", date(2025, 3, 31), "AAA", 1_000, date(2025, 5, 10))], None)
    repo.insert_holdings(db, other_manager, [
        _hold("B-1", date(2025, 3, 31), "BBB", 9_000, date(2025, 5, 10))], None)

    assert heal_13f_aum(db, manager) == (1, 0)
    assert heal_13f_aum(db, other_manager) == (1, 0)

    rows = db.execute(
        "SELECT manager_id, aum FROM aum_history"
        " WHERE as_of_date = '2025-03-31' AND source = '13f_total'"
        " ORDER BY manager_id"
    ).fetchall()
    assert len(rows) == 2, "each manager needs its own row for the quarter"
    assert {float(r["aum"]) for r in rows} == {1_000.0, 9_000.0}


def test_same_security_in_the_same_quarter_is_kept_per_manager(db, manager,
                                                               other_manager):
    """Two managers holding one CUSIP is normal, not a duplicate."""
    repo.insert_holdings(db, manager, [
        _hold("A-1", date(2025, 3, 31), "SAME", 1_000, date(2025, 5, 10))], None)
    inserted = repo.insert_holdings(db, other_manager, [
        _hold("B-1", date(2025, 3, 31), "SAME", 2_000, date(2025, 5, 10))], None)
    assert inserted == 1
    db.commit()  # queries.* open their own connection

    assert queries.us_holdings(manager)["rows"][0]["value_kusd"] == 1_000
    assert queries.us_holdings(other_manager)["rows"][0]["value_kusd"] == 2_000


def test_dashboard_queries_never_leak_across_managers(db, manager, other_manager):
    repo.insert_holdings(db, manager, [
        _hold("A-1", date(2025, 3, 31), "AAA", 1_000, date(2025, 5, 10))], None)
    heal_13f_aum(db, manager)
    db.commit()  # queries.* open their own connection

    assert queries.aum_series(manager)
    assert queries.aum_series(other_manager) == {}
    assert queries.aum_table(other_manager) == []
    assert queries.us_quarters(other_manager) == []
    assert queries.us_holdings(other_manager)["rows"] == []
    assert queries.changes(other_manager) == []
    assert queries.filing_status(other_manager) is None


def test_config_managers_are_registered_with_distinct_ciks(db):
    managers.sync_from_config(db)
    rows = managers.active(db)
    slugs = [m["slug"] for m in rows]
    assert "burgundy" in slugs and len(rows) >= 5

    ciks = [m["cik"] for m in rows if m["cik"]]
    assert len(ciks) == len(set(ciks)), "a CIK identifies one filer only"
    for m in rows:
        if m["cik"]:
            assert len(m["cik"]) == 10 and m["cik"].isdigit()


def test_sync_lets_config_correct_a_wrong_cik(db):
    """Config is authoritative: a manager pointed at the wrong filer is fixable.

    Tracking the wrong CIK is silent — the dashboard fills with another firm's
    portfolio and looks perfectly healthy — so the correction must not require
    touching the database by hand.
    """
    managers.sync_from_config(db)
    db.execute("UPDATE managers SET cik = NULL WHERE slug = 'mawer'")
    db.execute("UPDATE managers SET cik = '0009999999' WHERE slug = 'edgepoint'")

    managers.sync_from_config(db)
    assert managers.by_slug(db, "mawer")["cik"] == "0001538449"
    assert managers.by_slug(db, "edgepoint")["cik"] == "0001481669"
