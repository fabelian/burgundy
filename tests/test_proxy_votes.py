"""Voting records, and the band they open up.

A fact sheet prints the top 10–25 positions, so it cannot show a Korean holding
below its smallest printed weight — about $116M on the calibration document. A
voting record has no such ceiling and no weight either. The point of carrying
both is that their join separates three states which look identical in either
source alone, and the one that matters commercially — held, but too small to
print — is invisible without the pair.
"""
from __future__ import annotations

from datetime import date

from collectors.types import FundHoldingRow, ProxyVoteRow
from dashboard import queries
from parsers.securities import security_key
from pipeline import repo


def _fund(db, manager_id, slug="intl", name="International Equity"):
    db.execute(
        "INSERT INTO funds (manager_id, slug, name, mandate, cadence)"
        " VALUES (%s,%s,%s,'international','quarterly')"
        " ON CONFLICT (manager_id, slug) DO NOTHING",
        (manager_id, slug, name),
    )
    return db.execute(
        "SELECT id FROM funds WHERE manager_id = %s AND slug = %s",
        (manager_id, slug),
    ).fetchone()["id"]


def _vote(name="Samsung Electronics Co., Ltd.",
          meeting=date(2026, 3, 18), **kw):
    base = {"period_ended": date(2026, 6, 30), "meeting_date": meeting,
            "security_key": security_key(name), "issuer_name": name,
            "ballots": 7}
    return ProxyVoteRow(**{**base, **kw})


def _holding(name="Samsung Electronics Co Ltd", weight=2.8,
             as_of=date(2026, 6, 30), **kw):
    base = {"as_of_date": as_of, "security_key": security_key(name),
            "security_name": name, "weight": weight,
            "disclosure_scope": "top_n", "positions_listed": 25}
    return FundHoldingRow(**{**base, **kw})


# ---- classification ------------------------------------------------------

def test_a_korean_issuer_is_flagged_without_the_parser_asking():
    assert _vote().is_korean is True
    assert _vote(name="Nestle S.A.").is_korean is False


def test_the_country_column_still_wins_when_a_record_has_one():
    assert _vote(name="Samsung Electronics", country="Taiwan").is_korean is False


# ---- persistence ---------------------------------------------------------

def test_votes_insert_and_read_back(db, manager):
    fund_id = _fund(db, manager)
    assert repo.insert_proxy_votes(db, manager, fund_id, [_vote()], None) == 1

    row = db.execute("SELECT * FROM proxy_votes").fetchone()
    assert row["issuer_name"] == "Samsung Electronics Co., Ltd."
    assert row["meeting_date"] == date(2026, 3, 18)
    assert row["is_korean"] is True
    assert row["ballots"] == 7


def test_refetching_a_record_adds_nothing(db, manager):
    """A meeting on a given date is a historical fact; a re-fetch has nothing
    to correct."""
    fund_id = _fund(db, manager)
    repo.insert_proxy_votes(db, manager, fund_id, [_vote()], None)
    assert repo.insert_proxy_votes(db, manager, fund_id, [_vote()], None) == 0


def test_two_meetings_of_the_same_issuer_are_separate_evidence(db, manager):
    fund_id = _fund(db, manager)
    repo.insert_proxy_votes(db, manager, fund_id, [
        _vote(meeting=date(2025, 3, 19)), _vote(meeting=date(2026, 3, 18))], None)
    assert db.execute("SELECT count(*) c FROM proxy_votes").fetchone()["c"] == 2


def test_two_managers_voting_at_the_same_meeting_do_not_collide(db, manager,
                                                                other_manager):
    a, b = _fund(db, manager), _fund(db, other_manager)
    repo.insert_proxy_votes(db, manager, a, [_vote()], None)
    assert repo.insert_proxy_votes(db, other_manager, b, [_vote()], None) == 1


# ---- the three-way evidence view -----------------------------------------

def test_a_holding_in_both_sources_is_sized(db, manager):
    fund_id = _fund(db, manager)
    repo.insert_fund_holdings(db, manager, fund_id, [_holding()], None)
    repo.insert_proxy_votes(db, manager, fund_id, [_vote()], None)
    db.commit()  # queries.* open their own connection

    row = next(r for r in queries.kr_evidence(manager)
               if r["security_name"] == "Samsung Electronics Co Ltd")
    assert row["evidence"] == "sized"
    assert float(row["weight"]) == 2.8
    assert row["meeting_date"] == date(2026, 3, 18)


def test_a_vote_without_a_factsheet_line_is_the_sub_floor_band(db, manager):
    """The whole reason this source was built: the fact sheet cannot print this
    position, so without the voting record the manager looks like a non-holder."""
    fund_id = _fund(db, manager)
    repo.insert_fund_holdings(db, manager, fund_id, [
        _holding(name="SK hynix Inc", weight=3.0)], None)
    repo.insert_proxy_votes(db, manager, fund_id, [
        _vote(name="SK hynix Inc"), _vote(name="NAVER Corp")], None)
    db.commit()

    naver = next(r for r in queries.kr_evidence(manager)
                 if r["security_name"] == "NAVER Corp")
    assert naver["evidence"] == "unsized"
    assert naver["weight"] is None, "a voting record never states a size"
    assert naver["meeting_date"] == date(2026, 3, 18)


def test_a_factsheet_line_without_a_vote_is_not_treated_as_suspect(db, manager):
    """The voting record lags about 14 months, so a newly opened position is
    legitimately absent from it."""
    fund_id = _fund(db, manager)
    repo.insert_fund_holdings(db, manager, fund_id, [_holding()], None)
    db.commit()

    row = queries.kr_evidence(manager)[0]
    assert row["evidence"] == "recent"
    assert float(row["weight"]) == 2.8


def test_the_two_sources_join_across_differently_printed_names(db, manager):
    """A vote for 'Samsung Electronics Co., Ltd.' and a holding printed
    'Samsung Electronics Co Ltd' are one position, not two rows."""
    fund_id = _fund(db, manager)
    repo.insert_fund_holdings(db, manager, fund_id, [
        _holding(name="Samsung Electronics Co Ltd")], None)
    repo.insert_proxy_votes(db, manager, fund_id, [
        _vote(name="Samsung Electronics Co., Ltd.")], None)
    db.commit()

    rows = queries.kr_evidence(manager)
    assert len(rows) == 1
    assert rows[0]["evidence"] == "sized"


def test_non_korean_votes_stay_off_the_tab(db, manager):
    fund_id = _fund(db, manager)
    repo.insert_proxy_votes(db, manager, fund_id, [
        _vote(name="Nestle S.A."), _vote(name="Roche Holding AG"),
        _vote(name="Samsung Electronics Co Ltd")], None)
    db.commit()

    assert [r["security_name"] for r in queries.kr_evidence(manager)] == [
        "Samsung Electronics Co Ltd"]


def test_only_the_latest_meeting_of_each_issuer_is_shown(db, manager):
    fund_id = _fund(db, manager)
    repo.insert_proxy_votes(db, manager, fund_id, [
        _vote(meeting=date(2024, 3, 20)), _vote(meeting=date(2025, 3, 19)),
        _vote(meeting=date(2026, 3, 18))], None)
    db.commit()

    rows = queries.kr_evidence(manager)
    assert len(rows) == 1
    assert rows[0]["meeting_date"] == date(2026, 3, 18)


def test_weighted_rows_still_lead_the_table(db, manager):
    """Weight-ranked as before; rows with no size fall to the end rather than
    displacing a real number."""
    fund_id = _fund(db, manager)
    repo.insert_fund_holdings(db, manager, fund_id, [_holding(weight=2.8)], None)
    repo.insert_proxy_votes(db, manager, fund_id,
                            [_vote(name="NAVER Corp")], None)
    db.commit()

    rows = queries.kr_evidence(manager)
    assert [r["evidence"] for r in rows] == ["recent", "unsized"]
    assert rows[0]["weight"] is not None and rows[1]["weight"] is None


# ---- rendering -----------------------------------------------------------

def _render(**ctx):
    from dashboard.app import templates

    base = {"coverage": [], "evidence": [], "weight_series": {},
            "kr_series": {}, "history": [], "selected": "burgundy",
            "manager_name": "Test Manager", "configured_funds": 0}
    return templates.get_template("korea.html").render({**base, **ctx})


def _row(**kw):
    base = {"manager": "Mawer Investment Management", "manager_slug": "mawer",
            "fund": "Mawer International Equity Fund",
            "security_name": "Samsung Electronics Co Ltd", "weight": 2.8,
            "as_of_date": date(2026, 6, 30), "disclosure_scope": "top_n",
            "meeting_date": date(2026, 3, 18),
            "period_ended": date(2026, 6, 30), "evidence": "sized",
            "fund_nav": 7_251_500_000.0, "nav_currency": "CAD",
            "total_holdings": 72, "implied_value": 203_042_000.0}
    return {**base, **kw}


def test_the_sub_floor_band_is_explained_where_it_appears():
    html = _render(evidence=[_row(security_name="NAVER Corp", weight=None,
                                  as_of_date=None, disclosure_scope=None,
                                  evidence="unsized")])
    assert "규모 미상" in html
    assert "팩트시트 하한 미만" in html
    assert "팩트시트만으로는 존재 자체를 알 수 없습니다" in html


def test_a_sized_row_shows_its_weight_not_the_band_warning():
    html = _render(evidence=[_row()])
    assert "2.80%" in html
    assert "보유 확인 + 규모" in html
    assert "팩트시트 하한 미만" not in html


def test_a_factsheet_only_row_is_labelled_without_alarm():
    html = _render(evidence=[_row(meeting_date=None, evidence="recent")])
    assert "팩트시트만" in html
    assert "신규 편입된 포지션에서 정상적으로" in html
