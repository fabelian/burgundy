"""Recomputing derived rows must not require going back to SEC.

A scaling fix reaches the dashboard only when something recomputes the derived
AUM rows. Both other paths fetch first, which for years of history is slow
enough that a correction gets postponed — so this entrypoint exists to do it
from stored holdings alone.
"""
from datetime import date

import pytest

from collectors.types import HoldingRow
from pipeline import heal, managers, repo


def _filing(as_of, filed, count, value_each, shares_each=4_000_000):
    return [HoldingRow(as_of, filed, f"acc-{as_of}", False, f"C{i:04d}", f"N{i}",
                       shares_each, value_each, None, None)
            for i in range(count)]


@pytest.fixture
def cli(monkeypatch, db):
    monkeypatch.delenv("HEAL_MANAGER", raising=False)
    monkeypatch.setattr("sys.argv", ["heal"])
    return heal


def test_corrects_a_mis_scaled_quarter_without_fetching(cli, db, manager):
    # reported in thousands (implied ~$0.05/share) but stored unscaled
    repo.insert_holdings(db, manager,
                         _filing(date(2022, 12, 31), date(2023, 2, 14),
                                 76, 217_328, 4_000_000), None)
    db.execute(
        "INSERT INTO aum_history (manager_id, as_of_date, aum, currency, source)"
        " VALUES (%s, '2022-12-31', %s, 'USD', '13f_total')",
        (manager, 217_328 * 76))
    db.commit()

    cli.main()

    row = db.execute(
        "SELECT aum FROM aum_history WHERE as_of_date = '2022-12-31'").fetchone()
    assert float(row["aum"]) == 217_328 * 76 * 1000
    assert db.execute(
        "SELECT count(*) c FROM changes WHERE change_type = 'AUM_CORRECTED'"
    ).fetchone()["c"] == 1


def test_leaves_a_correct_quarter_alone(cli, db, manager):
    repo.insert_holdings(db, manager,
                         _filing(date(2022, 9, 30), date(2022, 11, 14),
                                 73, 202_586, 4_000_000), None)
    db.execute(
        "INSERT INTO aum_history (manager_id, as_of_date, aum, currency, source)"
        " VALUES (%s, '2022-09-30', %s, 'USD', '13f_total')",
        (manager, 202_586 * 73 * 1000))
    db.commit()

    cli.main()

    row = db.execute(
        "SELECT aum FROM aum_history WHERE as_of_date = '2022-09-30'").fetchone()
    assert float(row["aum"]) == 202_586 * 73 * 1000
    assert db.execute(
        "SELECT count(*) c FROM changes WHERE change_type = 'AUM_CORRECTED'"
    ).fetchone()["c"] == 0


def test_unknown_manager_fails_loudly(cli, db, monkeypatch):
    monkeypatch.setenv("HEAL_MANAGER", "nope")
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1


def test_scopes_to_one_manager(cli, db, manager, other_manager, monkeypatch):
    for mid in (manager, other_manager):
        repo.insert_holdings(db, mid,
                             _filing(date(2022, 12, 31), date(2023, 2, 14),
                                     10, 217_328, 4_000_000), None)
    db.commit()
    monkeypatch.setenv("HEAL_MANAGER", managers.by_slug(db, "mawer")["slug"])

    cli.main()

    rows = db.execute(
        "SELECT manager_id FROM aum_history WHERE source = '13f_total'").fetchall()
    assert [r["manager_id"] for r in rows] == [other_manager]


def test_reports_whether_the_unit_came_from_the_filing(cli, db, manager, capsys):
    """"corrected 0" alone cannot distinguish "already right" from "gave up".

    Without share counts the unit falls back to the filing date — the very rule
    that was wrong — and the run still prints corrected 0. The coverage figure
    is what tells the two apart.
    """
    repo.insert_holdings(db, manager,
                         _filing(date(2022, 12, 31), date(2023, 2, 14),
                                 10, 217_328, shares_each=0), None)
    db.commit()

    cli.main()

    out = capsys.readouterr().out
    assert "0/10 positions priced" in out
    assert "unit from filing DATE" in out


def test_explain_shows_the_multiplier_behind_each_quarter(cli, db, manager,
                                                          monkeypatch, capsys):
    monkeypatch.setenv("HEAL_EXPLAIN", "1")
    repo.insert_holdings(db, manager,
                         _filing(date(2022, 12, 31), date(2023, 2, 14),
                                 10, 217_328, shares_each=4_000_000), None)
    db.commit()

    cli.main()

    out = capsys.readouterr().out
    assert "median $/sh" in out
    assert "x1000" in out          # thousands inferred from ~$0.05/share
    assert "2022-12-31" in out
