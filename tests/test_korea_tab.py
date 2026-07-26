"""The Korea tab: what it shows, and what it must never let a reader conclude.

The tab exists for institutional sales prospecting, so its failure modes are
commercial rather than cosmetic. Showing one manager at a time makes the
comparison unanswerable; showing a stale quarter beside a current one invents a
change; and letting a top-ten fact sheet read as a full portfolio turns "not
printed" into "does not hold", which is the wrong thing to tell a salesperson
about to skip a call.
"""
from __future__ import annotations

from datetime import date

from collectors.types import FundHoldingRow
from dashboard import queries
from parsers.securities import security_key
from pipeline import repo


def _fund(db, manager_id, slug, name, mandate="international"):
    db.execute(
        "INSERT INTO funds (manager_id, slug, name, mandate, cadence)"
        " VALUES (%s,%s,%s,%s,'quarterly')"
        " ON CONFLICT (manager_id, slug) DO NOTHING",
        (manager_id, slug, name, mandate),
    )
    return db.execute(
        "SELECT id FROM funds WHERE manager_id = %s AND slug = %s",
        (manager_id, slug),
    ).fetchone()["id"]


def _row(name, weight, as_of=date(2024, 6, 30), scope="top_n", listed=10,
         rank=None, **kw):
    return FundHoldingRow(as_of_date=as_of, security_key=security_key(name),
                          security_name=name, weight=weight,
                          disclosure_scope=scope, positions_listed=listed,
                          position_rank=rank, **kw)


def _render(**ctx):
    from dashboard.app import templates

    base = {"coverage": [], "evidence": [], "weight_series": {},
            "kr_series": {}, "history": [], "selected": "burgundy",
            "configured_funds": 0}
    return templates.get_template("korea.html").render({**base, **ctx})


# ---- the query -----------------------------------------------------------

def test_korean_holdings_span_every_manager(db, manager, other_manager):
    """The tab answers 'which of the five holds Samsung' — scoping it to the
    selected manager would mean clicking through all five to find out."""
    a = _fund(db, manager, "intl", "A International")
    b = _fund(db, other_manager, "intl", "B International")
    repo.insert_fund_holdings(db, manager, a,
                              [_row("Samsung Electronics Co Ltd", 1.7)], None)
    repo.insert_fund_holdings(db, other_manager, b,
                              [_row("SK Hynix Inc", 0.9)], None)
    db.commit()  # queries.* open their own connection

    rows = queries.kr_evidence()

    assert {r["security_name"] for r in rows} == {"Samsung Electronics Co Ltd",
                                                 "SK Hynix Inc"}
    assert len({r["manager"] for r in rows}) == 2


def test_non_korean_positions_are_excluded(db, manager):
    fund_id = _fund(db, manager, "intl", "A International")
    repo.insert_fund_holdings(db, manager, fund_id, [
        _row("Samsung Electronics Co Ltd", 1.7),
        _row("Nestle S.A.", 3.1),
        _row("Taiwan Semiconductor Manufacturing Co Ltd", 2.5),
    ], None)
    db.commit()

    assert [r["security_name"] for r in queries.kr_evidence()] == [
        "Samsung Electronics Co Ltd"]


def test_only_the_latest_period_of_each_fund_is_shown(db, manager):
    """Stacking quarters would show one position four times and read as four
    holdings."""
    fund_id = _fund(db, manager, "intl", "A International")
    repo.insert_fund_holdings(db, manager, fund_id, [
        _row("Samsung Electronics Co Ltd", 1.4, as_of=date(2024, 3, 31))], None)
    repo.insert_fund_holdings(db, manager, fund_id, [
        _row("Samsung Electronics Co Ltd", 1.7, as_of=date(2024, 6, 30))], None)
    db.commit()

    rows = queries.kr_evidence()
    assert len(rows) == 1
    assert rows[0]["as_of_date"] == date(2024, 6, 30)
    assert float(rows[0]["weight"]) == 1.7


def test_holdings_are_ranked_by_weight_for_the_sales_question(db, manager,
                                                              other_manager):
    a = _fund(db, manager, "intl", "A International")
    b = _fund(db, other_manager, "intl", "B International")
    repo.insert_fund_holdings(db, manager, a,
                              [_row("SK Hynix Inc", 0.9)], None)
    repo.insert_fund_holdings(db, other_manager, b,
                              [_row("Samsung Electronics Co Ltd", 2.4)], None)
    db.commit()

    assert [float(r["weight"]) for r in queries.kr_evidence()] == [2.4, 0.9]


def test_the_weight_trend_keeps_every_period(db, manager):
    fund_id = _fund(db, manager, "intl", "A International")
    for as_of, weight in ((date(2024, 3, 31), 1.4), (date(2024, 6, 30), 1.7)):
        repo.insert_fund_holdings(db, manager, fund_id, [
            _row("Samsung Electronics Co Ltd", weight, as_of=as_of)], None)
    db.commit()

    series = queries.kr_weight_series()
    assert len(series) == 1
    assert [p["y"] for p in next(iter(series.values()))] == [1.4, 1.7]


def test_coverage_lists_a_tracked_fund_with_nothing_collected(db, manager):
    """A fund with no document read is unknown, not empty — the two must not
    look the same."""
    _fund(db, manager, "intl", "A International")
    db.commit()

    coverage = queries.kr_fund_coverage()
    assert len(coverage) == 1
    assert coverage[0]["fund"] == "A International"
    assert coverage[0]["latest_as_of"] is None


def test_coverage_reports_the_freshest_document_per_fund(db, manager):
    fund_id = _fund(db, manager, "intl", "A International")
    repo.insert_fund_holdings(db, manager, fund_id, [
        _row("Nestle S.A.", 3.0, as_of=date(2024, 3, 31))], None)
    repo.insert_fund_holdings(db, manager, fund_id, [
        _row("Nestle S.A.", 3.1, as_of=date(2024, 6, 30)),
        _row("Samsung Electronics Co Ltd", 1.7, as_of=date(2024, 6, 30))], None)
    db.commit()

    row = queries.kr_fund_coverage()[0]
    assert row["latest_as_of"] == date(2024, 6, 30)
    assert row["positions"] == 2


# ---- the rendering -------------------------------------------------------

def _holding(**kw):
    base = {"manager": "Mawer Investment Management", "manager_slug": "mawer",
            "fund": "Mawer International Equity Fund",
            "as_of_date": date(2024, 6, 30),
            "security_name": "Samsung Electronics Co Ltd", "weight": 1.7,
            "disclosure_scope": "top_n", "meeting_date": None,
            "period_ended": None, "evidence": "recent"}
    return {**base, **kw}


def test_a_holding_renders_with_its_manager_and_weight():
    html = _render(evidence=[_holding()])
    assert "Mawer Investment Management" in html
    assert "Samsung Electronics Co Ltd" in html
    assert "1.70%" in html


def test_a_top_n_sheet_warns_that_absence_proves_nothing():
    """The commercial trap: reading a manager's absence from a top-N list as
    'does not hold' would talk a salesperson out of a real call."""
    html = _render(evidence=[_holding(disclosure_scope="top_n")])
    assert "보유하지 않는다는 뜻은 아닙니다" in html
    assert "상위 N종목만" in html


def test_a_full_portfolio_source_carries_no_such_warning():
    """What a vendor feed with complete holdings would look like — the warning
    has to stop firing, or it trains the reader to ignore it."""
    html = _render(evidence=[_holding(disclosure_scope="full")])
    assert "전체 포트폴리오" in html
    assert "보유하지 않는다는 뜻은 아닙니다" not in html


def test_a_configured_but_unsynced_registry_does_not_read_as_untracked():
    """The registry is filled by pipeline.run, not the dashboard, so between a
    deploy and the next collector run the table is empty while config is not.
    Reporting "no funds tracked" there states the opposite of the truth — the
    same empty-reads-as-a-conclusion failure this tab exists to prevent."""
    html = _render(coverage=[], configured_funds=1)

    assert "동기화되지 않았습니다" in html
    assert "추적 중인 펀드가 없습니다" not in html


def test_an_empty_config_still_says_nothing_is_tracked():
    html = _render(coverage=[], configured_funds=0)

    assert "추적 중인 펀드가 없습니다" in html
    assert "동기화되지 않았습니다" not in html


def test_the_uncollected_state_points_at_the_collector_panel():
    """'No fact sheets yet' has two causes — the collector has not run, or it
    ran and the layout was not recognised — and they need different actions."""
    html = _render(coverage=[], configured_funds=1)

    assert "Overview 탭의 컬렉터 패널" in html
    assert "new_rows = 0" in html


def test_nothing_collected_and_nothing_korean_read_differently():
    """Both tables are empty; only one of them means the managers hold no
    Korean large caps."""
    uncollected = _render(coverage=[{"manager": "M", "manager_slug": "m",
                                     "fund": "F", "mandate": "international",
                                     "cadence": "quarterly",
                                     "latest_as_of": None, "positions": None,
                                     "disclosure_scope": None}])
    collected = _render(coverage=[{"manager": "M", "manager_slug": "m",
                                   "fund": "F", "mandate": "international",
                                   "cadence": "quarterly",
                                   "latest_as_of": date(2024, 6, 30),
                                   "positions": 10,
                                   "disclosure_scope": "top_n"}])

    assert "아직 수집된 팩트시트가 없습니다" in uncollected
    assert "아직 수집된 팩트시트가 없습니다" not in collected
    assert "한국 종목이 확인되지 않았습니다" in collected
    assert "미수집" in uncollected


def test_the_dart_section_survives_as_the_documented_safety_net():
    """It stays on the tab, below the fund holdings, explained rather than
    presented as the main answer."""
    html = _render(history=[{"filed_at": date(2024, 5, 1),
                             "as_of_date": date(2024, 4, 30),
                             "corp_name": "오성첨단소재", "ticker": "052420",
                             "shares": 1000, "ownership_pct": 5.4,
                             "report_type": "신규", "rcept_no": "2024050100001"}])
    assert "DART 5% 대량보유 공시" in html
    assert "오성첨단소재" in html
    assert "대형주는 여기 나타나지 않습니다" in html
    assert html.index("한국 보유 종목") < html.index("DART 5% 대량보유 공시")


def test_chart_payloads_still_render_as_executable_javascript():
    html = _render(weight_series={"Mawer · Samsung Electronics": [
        {"x": "2024-06-30", "y": 1.7}]})
    assert "&#34;" not in html and "&quot;" not in html
    assert '"Mawer \\u00b7 Samsung Electronics"' in html or \
           '"Mawer · Samsung Electronics"' in html
