"""Diff-logic tests against a real Postgres (skipped if unavailable)."""
from datetime import date

from collectors.types import HoldingRow, KrHoldingRow, PersonnelRow
from parsers.parse_dart import parse_dart_majorstock
from pipeline import diff, repo


def _holding(acc, as_of, cusip, shares, value, amend=False):
    return HoldingRow(
        as_of_date=as_of, filed_at=as_of, accession_no=acc, is_amendment=amend,
        cusip=cusip, name=f"NAME {cusip}", shares=shares, value_kusd=value,
        ticker=None, weight=None,
    )


def _changes(conn, entity_type=None):
    q = "SELECT * FROM changes"
    params = ()
    if entity_type:
        q += " WHERE entity_type = %s"
        params = (entity_type,)
    q += " ORDER BY id"
    return conn.execute(q, params).fetchall()


# ---- US holdings ---------------------------------------------------------

def test_us_holding_diff_new_exit_increase_decrease(db):
    q1 = "0000000000-24-000001"
    q2 = "0000000000-24-000002"
    # Q1: AAPL 1000, MSFT 500
    repo.insert_holdings(db, [
        _holding(q1, date(2024, 3, 31), "AAA", 1000, 100),
        _holding(q1, date(2024, 3, 31), "BBB", 500, 50),
    ], None)
    diff.diff_us_holdings(db, q1)  # first filing: no diff
    assert len(_changes(db)) == 0

    # Q2: AAPL 1500 (increase), BBB gone (exit), CCC new
    repo.insert_holdings(db, [
        _holding(q2, date(2024, 6, 30), "AAA", 1500, 150),
        _holding(q2, date(2024, 6, 30), "CCC", 200, 20),
    ], None)
    diff.diff_us_holdings(db, q2)

    by_type = {c["change_type"]: c for c in _changes(db)}
    assert set(by_type) == {"INCREASED", "EXITED", "NEW_POSITION"}
    assert by_type["INCREASED"]["entity_key"] == "AAA"
    assert by_type["INCREASED"]["before"]["shares"] == 1000
    assert by_type["INCREASED"]["after"]["shares"] == 1500
    assert by_type["EXITED"]["entity_key"] == "BBB"
    assert by_type["NEW_POSITION"]["entity_key"] == "CCC"


def test_us_holding_diff_idempotent(db):
    q1 = "0000000000-24-000001"
    q2 = "0000000000-24-000002"
    repo.insert_holdings(db, [_holding(q1, date(2024, 3, 31), "AAA", 1000, 100)], None)
    repo.insert_holdings(db, [_holding(q2, date(2024, 6, 30), "AAA", 1500, 150)], None)
    diff.diff_us_holdings(db, q2)
    diff.diff_us_holdings(db, q2)  # re-run
    assert len(_changes(db)) == 1


def test_amendment_adds_row_not_update(db):
    orig = "0000000000-24-000001"
    amend = "0000000000-24-000002"
    repo.insert_holdings(db, [_holding(orig, date(2024, 3, 31), "AAA", 1000, 100)], None)
    repo.insert_holdings(db, [_holding(amend, date(2024, 3, 31), "AAA", 1100, 110,
                                       amend=True)], None)
    rows = db.execute("SELECT accession_no, shares FROM holdings ORDER BY id").fetchall()
    assert len(rows) == 2  # original untouched, amendment appended
    assert rows[0]["shares"] == 1000
    assert rows[1]["shares"] == 1100


# ---- Korean holdings -----------------------------------------------------

def test_kr_stake_changed(db):
    repo.insert_kr_holdings(db, [KrHoldingRow(
        as_of_date=date(2024, 1, 1), filed_at=date(2024, 1, 1), rcept_no="R1",
        corp_code="C1", corp_name="Corp", shares=1000, ownership_pct=5.0)], None)
    repo.insert_kr_holdings(db, [KrHoldingRow(
        as_of_date=date(2024, 3, 1), filed_at=date(2024, 3, 1), rcept_no="R2",
        corp_code="C1", corp_name="Corp", shares=1400, ownership_pct=6.5)], None)
    diff.diff_kr_holdings(db, "R2", "C1")
    changes = _changes(db, "kr_holding")
    assert len(changes) == 1
    assert changes[0]["change_type"] == "STAKE_CHANGED"
    assert float(changes[0]["before"]["ownership_pct"]) == 5.0
    assert float(changes[0]["after"]["ownership_pct"]) == 6.5


# ---- Personnel SCD2 ------------------------------------------------------

def test_personnel_scd2_title_change_keeps_two_rows(db):
    p_v1 = [PersonnelRow("Jane Doe", "Analyst", "website_team", date(2024, 1, 1))]
    diff.reconcile_personnel(db, "website_team", p_v1, date(2024, 1, 1), None)

    p_v2 = [PersonnelRow("Jane Doe", "Portfolio Manager", "website_team",
                         date(2024, 6, 1))]
    diff.reconcile_personnel(db, "website_team", p_v2, date(2024, 6, 1), None)

    rows = db.execute(
        "SELECT title, valid_from, valid_to FROM personnel "
        "WHERE person_name = 'Jane Doe' ORDER BY valid_from").fetchall()
    assert len(rows) == 2
    assert rows[0]["title"] == "Analyst"
    assert rows[0]["valid_to"] == date(2024, 6, 1)   # closed
    assert rows[1]["title"] == "Portfolio Manager"
    assert rows[1]["valid_to"] is None               # current

    types = {c["change_type"] for c in _changes(db, "personnel")}
    assert "PERSON_JOINED" in types
    assert "TITLE_CHANGED" in types


def test_personnel_join_and_leave(db):
    diff.reconcile_personnel(db, "website_team",
                             [PersonnelRow("A B", "CEO", "website_team",
                                           date(2024, 1, 1))],
                             date(2024, 1, 1), None)
    # next scrape: A B gone, C D joined
    diff.reconcile_personnel(db, "website_team",
                             [PersonnelRow("C D", "CFO", "website_team",
                                           date(2024, 2, 1))],
                             date(2024, 2, 1), None)
    types = {c["change_type"] for c in _changes(db, "personnel")}
    assert {"PERSON_JOINED", "PERSON_LEFT"}.issubset(types)
    ab = db.execute("SELECT valid_to FROM personnel WHERE person_name='A B'").fetchone()
    assert ab["valid_to"] == date(2024, 2, 1)


# ---- DART parser + AUM diff ---------------------------------------------

def test_dart_parser_filters_reporter():
    import pathlib
    payload = (pathlib.Path(__file__).parent / "fixtures"
               / "sample_dart_majorstock.json").read_text(encoding="utf-8")
    rows = parse_dart_majorstock(payload, search_terms=["버건디", "Burgundy"])
    # two Burgundy rows (English + Korean name), 국민연금 excluded
    assert len(rows) == 2
    corps = {r.rcept_no for r in rows}
    assert corps == {"20240102000123", "20230815000555"}
    r = next(x for x in rows if x.rcept_no == "20240102000123")
    assert r.shares == 1_500_000
    assert float(r.ownership_pct) == 6.12
