"""fund_holdings: the table the Korea tab is built on.

What is worth pinning down here is not that an insert works, but that the
things which would quietly mislead a sales call cannot happen: a re-issued fact
sheet leaving a stale weight on screen, a Korean position landing unclassified,
or one manager's disclosure showing up under another's name.
"""
from __future__ import annotations

from datetime import date

import pytest

from collectors.types import FundHoldingRow
from pipeline import funds, repo


def _fund(db, manager_id, slug="international-equity"):
    db.execute(
        """
        INSERT INTO funds (manager_id, slug, name, mandate, cadence)
        VALUES (%s, %s, %s, 'international', 'quarterly')
        ON CONFLICT (manager_id, slug) DO NOTHING
        """,
        (manager_id, slug, f"Test {slug}"),
    )
    return db.execute(
        "SELECT id FROM funds WHERE manager_id = %s AND slug = %s",
        (manager_id, slug),
    ).fetchone()["id"]


def _row(name="Samsung Electronics Co Ltd", weight=1.7, **kw):
    from parsers.securities import security_key

    base = {"as_of_date": date(2024, 6, 30), "security_key": security_key(name),
            "security_name": name, "weight": weight, "position_rank": 3,
            "disclosure_scope": "top_n", "positions_listed": 10}
    return FundHoldingRow(**{**base, **kw})


# ---- classification ------------------------------------------------------

def test_korean_flag_is_set_without_the_parser_asking():
    """Classification lives in the row type, so no future fact-sheet parser can
    write a Samsung position the Korea tab then fails to show."""
    assert _row().is_korean is True
    assert _row(name="Nestle S.A.").is_korean is False


def test_country_column_from_the_document_is_honoured():
    assert _row(name="Anything Ltd", country="South Korea").is_korean is True
    assert _row(name="Samsung Electronics", country="Taiwan").is_korean is False


def test_explicit_flag_overrides_detection():
    assert _row(name="Nestle S.A.", is_korean=True).is_korean is True


# ---- persistence ---------------------------------------------------------

def test_insert_and_read_back(db, manager):
    fund_id = _fund(db, manager)
    assert repo.insert_fund_holdings(db, manager, fund_id, [_row()], None) == 1

    row = db.execute("SELECT * FROM fund_holdings").fetchone()
    assert row["security_name"] == "Samsung Electronics Co Ltd"
    assert float(row["weight"]) == pytest.approx(1.7)
    assert row["is_korean"] is True
    assert row["disclosure_scope"] == "top_n"
    assert row["positions_listed"] == 10


def test_refetching_the_same_document_adds_nothing(db, manager):
    fund_id = _fund(db, manager)
    repo.insert_fund_holdings(db, manager, fund_id, [_row()], None)
    assert repo.insert_fund_holdings(db, manager, fund_id, [_row()], None) == 0
    assert db.execute("SELECT count(*) c FROM fund_holdings").fetchone()["c"] == 1


def test_a_reissued_factsheet_corrects_the_weight(db, manager):
    """A manager re-publishing a sheet with a fixed number must not leave the
    old one on screen — unlike a 13F amendment, there is no second accession
    number under which both versions could stand."""
    fund_id = _fund(db, manager)
    repo.insert_fund_holdings(db, manager, fund_id, [_row(weight=1.7)], None)
    inserted = repo.insert_fund_holdings(db, manager, fund_id,
                                         [_row(weight=2.4)], None)

    assert inserted == 0, "a correction is not new coverage"
    rows = db.execute("SELECT weight FROM fund_holdings").fetchall()
    assert len(rows) == 1
    assert float(rows[0]["weight"]) == pytest.approx(2.4)


def test_the_preferred_line_is_kept_alongside_the_common(db, manager):
    fund_id = _fund(db, manager)
    n = repo.insert_fund_holdings(db, manager, fund_id, [
        _row(name="Samsung Electronics Co Ltd", weight=1.7),
        _row(name="Samsung Electronics Co Ltd Pref", weight=0.8),
    ], None)
    assert n == 2


def test_a_later_period_is_a_new_row_not_an_overwrite(db, manager):
    fund_id = _fund(db, manager)
    repo.insert_fund_holdings(db, manager, fund_id, [_row()], None)
    repo.insert_fund_holdings(db, manager, fund_id,
                              [_row(as_of_date=date(2024, 9, 30))], None)
    assert db.execute("SELECT count(*) c FROM fund_holdings").fetchone()["c"] == 2


def test_two_managers_holding_the_same_security_do_not_collide(db, manager,
                                                               other_manager):
    a = _fund(db, manager)
    b = _fund(db, other_manager)
    repo.insert_fund_holdings(db, manager, a, [_row()], None)
    assert repo.insert_fund_holdings(db, other_manager, b, [_row()], None) == 1

    owners = db.execute(
        "SELECT manager_id FROM fund_holdings ORDER BY manager_id").fetchall()
    assert sorted(r["manager_id"] for r in owners) == sorted([manager,
                                                              other_manager])


# ---- registry ------------------------------------------------------------

def test_config_funds_sync_into_the_table(db, manager):
    from pipeline import managers as managers_mod

    managers_mod.sync_from_config(db)
    funds.sync_from_config(db)

    rows = db.execute("SELECT slug, mandate, doc_url_template FROM funds").fetchall()
    assert rows, "config.FUNDS should seed at least the confirmed Mawer fund"
    for r in rows:
        assert r["mandate"] in ("international", "global", "emerging"), (
            "a Canadian or US-only mandate cannot hold a Korean security")
        assert r["doc_url_template"], "a fund with no document URL is unreadable"


def test_sync_is_idempotent(db, manager):
    funds.sync_from_config(db)
    before = db.execute("SELECT count(*) c FROM funds").fetchone()["c"]
    funds.sync_from_config(db)
    assert db.execute("SELECT count(*) c FROM funds").fetchone()["c"] == before


def test_a_fund_naming_an_unknown_manager_is_skipped_not_invented(db, manager,
                                                                  monkeypatch):
    import config

    monkeypatch.setattr(config, "FUNDS", [{
        "manager_slug": "no-such-manager", "slug": "x", "name": "X",
        "mandate": "global", "doc_url_template": "https://example.com/x.pdf",
    }])
    assert funds.sync_from_config(db) == 0
    assert db.execute("SELECT count(*) c FROM managers WHERE slug='no-such-manager'"
                      ).fetchone()["c"] == 0
