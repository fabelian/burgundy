"""A DART run that finds nothing must not look like one that failed.

The collector reported ok / 0 rows for Burgundy. That is the correct answer for
a quiet window, and it was also what a rejected API key produced — the failure
was swallowed into an empty list. These tests pin the difference, plus the
paging and window handling a historical backfill depends on.
"""
from datetime import date, timedelta

import pytest

from collectors import dart_5pct
from collectors.dart_5pct import Dart5pctCollector

MANAGER = {"id": 1, "slug": "burgundy", "dart_terms": ["버건디", "Burgundy"]}


def _entry(corp_code, report_nm="주식등의 대량보유상황보고서"):
    return {"corp_code": corp_code, "stock_code": "005930",
            "report_nm": report_nm}


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setattr(dart_5pct.config, "DART_API_KEY", "test-key")


def _stub_list(monkeypatch, pages):
    """pages: dict keyed by page_no -> payload, or a callable(params)."""
    calls = []

    def fake_get_json(url, params=None):
        calls.append(params or {})
        if callable(pages):
            return pages(params or {})
        return pages[int((params or {}).get("page_no", 1))]

    monkeypatch.setattr(dart_5pct, "get_json", fake_get_json)
    return calls


def test_no_disclosures_is_an_empty_result_not_an_error(monkeypatch):
    _stub_list(monkeypatch, {1: {"status": "013", "message": "no data"}})
    assert Dart5pctCollector(MANAGER).discover() == []


def test_a_rejected_key_raises_instead_of_looking_quiet(monkeypatch):
    _stub_list(monkeypatch, {1: {"status": "020", "message": "요청 제한 초과"}})
    with pytest.raises(RuntimeError) as exc:
        Dart5pctCollector(MANAGER).discover()
    assert "020" in str(exc.value)


def test_every_page_is_read(monkeypatch):
    pages = {
        1: {"status": "000", "total_page": 3, "list": [_entry("A")]},
        2: {"status": "000", "total_page": 3, "list": [_entry("B")]},
        3: {"status": "000", "total_page": 3, "list": [_entry("C")]},
    }
    _stub_list(monkeypatch, pages)
    targets = Dart5pctCollector(MANAGER).discover()
    assert {t.meta["corp_code"] for t in targets} == {"A", "B", "C"}


def test_non_ownership_reports_are_ignored(monkeypatch):
    _stub_list(monkeypatch, {1: {"status": "000", "total_page": 1, "list": [
        _entry("A"), _entry("B", report_nm="분기보고서")]}})
    targets = Dart5pctCollector(MANAGER).discover()
    assert [t.meta["corp_code"] for t in targets] == ["A"]


def test_a_historical_window_is_chunked(monkeypatch):
    calls = _stub_list(monkeypatch, lambda params: {
        "status": "000", "total_page": 1, "list": []})
    Dart5pctCollector(MANAGER, since=date(2015, 1, 1)).discover()

    assert len(calls) > 20, "a decade must not be asked for in one request"
    spans = [(c["bgn_de"], c["end_de"]) for c in calls]
    assert spans[0][0] == "20150101"
    assert spans == sorted(spans), "windows are scanned oldest first"
    assert len(spans) == len(set(spans)), "no window is scanned twice"


def test_the_daily_collector_only_looks_back_a_few_days(monkeypatch):
    calls = _stub_list(monkeypatch, lambda params: {
        "status": "000", "total_page": 1, "list": []})
    Dart5pctCollector(MANAGER, lookback_days=3).discover()

    assert len(calls) == 1
    start = date(*map(int, [calls[0]["bgn_de"][:4], calls[0]["bgn_de"][4:6],
                            calls[0]["bgn_de"][6:]]))
    assert date.today() - start == timedelta(days=3)


def test_limit_caps_issuers_so_a_backfill_can_be_split(monkeypatch):
    _stub_list(monkeypatch, {1: {"status": "000", "total_page": 1,
                                 "list": [_entry(c) for c in "ABCDE"]}})
    targets = Dart5pctCollector(MANAGER, limit=2).discover()
    assert len(targets) == 2


def test_a_manager_without_search_terms_does_not_apply():
    assert not Dart5pctCollector({"id": 2, "slug": "mawer",
                                  "dart_terms": []}).applies()
    assert Dart5pctCollector(MANAGER).applies()
