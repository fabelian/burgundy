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
    # a non-empty sweep, so the empty-result re-check does not add a second pass
    calls = _stub_list(monkeypatch, lambda params: {
        "status": "000", "total_page": 1, "list": [_entry("A")]})
    Dart5pctCollector(MANAGER, since=date(2015, 1, 1)).discover()

    assert len(calls) > 20, "a decade must not be asked for in one request"
    spans = [(c["bgn_de"], c["end_de"]) for c in calls]
    assert spans[0][0] == "20150101"
    assert spans == sorted(spans), "windows are scanned oldest first"
    assert len(spans) == len(set(spans)), "no window is scanned twice"


def test_the_daily_collector_only_looks_back_a_few_days(monkeypatch):
    calls = _stub_list(monkeypatch, lambda params: {
        "status": "000", "total_page": 1, "list": [_entry("A")]})
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


def test_a_quota_hit_partway_keeps_what_was_already_found(monkeypatch):
    """A years-long sweep can exhaust the daily quota mid-run.

    Discarding thousands of issuers already discovered would make the whole run
    worthless, so the scan stops and returns them instead.
    """
    state = {"n": 0}

    def pages(params):
        state["n"] += 1
        if state["n"] == 1:
            return {"status": "000", "total_page": 1, "list": [_entry("A")]}
        return {"status": "020", "message": "요청 제한 초과"}

    _stub_list(monkeypatch, pages)
    targets = Dart5pctCollector(MANAGER, since=date(2015, 1, 1)).discover()
    assert [t.meta["corp_code"] for t in targets] == ["A"]


def test_failing_before_anything_is_found_still_raises(monkeypatch):
    """With nothing collected, the failure is the entire result — never hide it."""
    _stub_list(monkeypatch, lambda params: {"status": "020", "message": "quota"})
    with pytest.raises(dart_5pct.DartError):
        Dart5pctCollector(MANAGER, since=date(2015, 1, 1)).discover()


def test_json_calls_are_throttled(monkeypatch):
    """Thousands of unthrottled calls reach the quota at network speed."""
    import config as cfg
    from collectors import http as http_mod

    assert cfg.JSON_RATE_LIMIT_SLEEP > 0
    slept = []
    monkeypatch.setattr(http_mod.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(http_mod, "_client",
                        lambda: _FakeClient())
    http_mod._last_json_request[0] = http_mod.time.monotonic()
    http_mod.get_json("https://example.test/api")
    assert slept, "a back-to-back call must wait"


def test_json_calls_reuse_one_connection(monkeypatch):
    """A per-call connection pays a TCP and TLS handshake every time."""
    from collectors import http as http_mod

    http_mod._json_client[0] = None
    first, second = http_mod._client(), http_mod._client()
    assert first is second, "the client must be shared, not rebuilt per call"
    http_mod._json_client[0] = None


class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"status": "000", "list": []}


class _FakeClient:
    def get(self, *a, **k):
        return _FakeResp()


def test_asks_only_for_major_holding_reports(monkeypatch):
    """지분공시 as a whole is dominated by 임원·주요주주 소유상황보고.

    Requesting the broad type pushes a 90-day window past the page cap, which
    drops issuers off the end without saying so.
    """
    calls = _stub_list(monkeypatch, {1: {"status": "000", "total_page": 1,
                                         "list": [_entry("A")]}})
    Dart5pctCollector(MANAGER).discover()
    assert calls[0].get("pblntf_detail_ty") == "D001"
    assert "pblntf_ty" not in calls[0]


def test_falls_back_when_the_detail_code_is_rejected(monkeypatch):
    seen = []

    def pages(params):
        seen.append(dict(params))
        if "pblntf_detail_ty" in params:
            return {"status": "100", "message": "부적절한 필드"}
        return {"status": "000", "total_page": 1, "list": [_entry("A")]}

    _stub_list(monkeypatch, pages)
    targets = Dart5pctCollector(MANAGER).discover()
    assert [t.meta["corp_code"] for t in targets] == ["A"]
    assert seen[-1].get("pblntf_ty") == "D"


def test_a_truncated_window_is_reported(monkeypatch, capsys):
    """Silently keeping the first 100 pages would look like a complete sweep."""
    _stub_list(monkeypatch, lambda params: {
        "status": "000", "total_page": 400, "list": [_entry("A")]})
    Dart5pctCollector(MANAGER).discover()
    out = capsys.readouterr().out
    assert "WARNING" in out and "400" in out


def test_an_empty_detail_sweep_is_confirmed_against_the_broad_type(monkeypatch):
    """An empty answer and a wrong detail code look identical.

    Left unchecked, a bad code would report "no Korean holdings" — a wrong
    conclusion about the firm, not just a missing row.
    """
    seen = []

    def pages(params):
        seen.append(dict(params))
        if "pblntf_detail_ty" in params:
            return {"status": "013", "message": "no data"}
        return {"status": "000", "total_page": 1, "list": [_entry("A")]}

    _stub_list(monkeypatch, pages)
    targets = Dart5pctCollector(MANAGER).discover()

    assert [t.meta["corp_code"] for t in targets] == ["A"]
    assert any("pblntf_detail_ty" in c for c in seen)
    assert any(c.get("pblntf_ty") == "D" for c in seen)
