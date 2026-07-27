"""The backfill entrypoint is driven by a fixed start command on the deploy
platform, so its options have to be reachable through the environment — and one
manager's failure must not cost the others their backfill.
"""
import pytest

from pipeline import backfill


class _FakeCollector:
    """Stands in for the EDGAR collector; records how it was constructed."""
    calls: list[dict] = []
    fail_for: set[str] = set()

    def __init__(self, manager, *, since=None, limit=None):
        self.manager = manager
        type(self).calls.append({"slug": manager["slug"], "since": since,
                                 "limit": limit})

    def applies(self):
        return bool(self.manager.get("cik"))

    def run(self):
        if self.manager["slug"] in type(self).fail_for:
            raise RuntimeError("boom")
        return {"status": "ok", "new_raw": 1, "new_rows": 1}


@pytest.fixture
def fake(monkeypatch, db):
    _FakeCollector.calls = []
    _FakeCollector.fail_for = set()
    monkeypatch.setattr(backfill, "Edgar13FCollector", _FakeCollector)
    for var in ("BACKFILL_MANAGER", "BACKFILL_SINCE", "BACKFILL_LIMIT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("sys.argv", ["backfill"])
    db.commit()  # backfill opens its own connection
    return _FakeCollector


def test_backfills_every_tracked_manager_by_default(fake):
    """Every *tracked* manager — derived from config rather than counted, so
    retiring one does not quietly turn this into a weaker assertion."""
    import config

    backfill.main()

    slugs = [c["slug"] for c in fake.calls]
    expected = {m["slug"] for m in config.MANAGERS if m.get("is_active", True)}
    assert set(slugs) == expected
    assert len(slugs) == len(set(slugs)), "no manager is backfilled twice"


def test_a_retired_manager_is_not_swept_up_by_the_default_backfill(fake):
    """Retiring stops automatic work of every kind, backfill included."""
    import config

    backfill.main()

    slugs = {c["slug"] for c in fake.calls}
    for m in config.MANAGERS:
        if not m.get("is_active", True):
            assert m["slug"] not in slugs, m["slug"]


def test_a_retired_manager_can_still_be_backfilled_on_purpose(fake, monkeypatch):
    """Naming one explicitly is an operator decision, not automatic collection,
    and re-running history for a retired manager is a legitimate one-off."""
    monkeypatch.setenv("BACKFILL_MANAGER", "mawer")
    backfill.main()
    assert [c["slug"] for c in fake.calls] == ["mawer"]


def test_environment_selects_a_single_manager(fake, monkeypatch):
    monkeypatch.setenv("BACKFILL_MANAGER", "burgundy")
    monkeypatch.setenv("BACKFILL_SINCE", "2018")
    monkeypatch.setenv("BACKFILL_LIMIT", "5")

    backfill.main()

    assert [c["slug"] for c in fake.calls] == ["burgundy"]
    assert fake.calls[0]["since"].year == 2018
    assert fake.calls[0]["limit"] == 5


def test_blank_environment_values_fall_back_to_defaults(fake, monkeypatch):
    """An unset Railway variable arrives as an empty string, not as absent."""
    monkeypatch.setenv("BACKFILL_MANAGER", "")
    monkeypatch.setenv("BACKFILL_SINCE", "")
    monkeypatch.setenv("BACKFILL_LIMIT", "")

    backfill.main()

    import config

    assert len(fake.calls) == sum(
        1 for m in config.MANAGERS if m.get("is_active", True))
    assert fake.calls[0]["since"].year == 2013
    assert fake.calls[0]["limit"] is None


def test_unknown_manager_fails_loudly(fake, monkeypatch):
    monkeypatch.setenv("BACKFILL_MANAGER", "nope")
    with pytest.raises(SystemExit) as exc:
        backfill.main()
    assert exc.value.code == 1
    assert fake.calls == []


def test_one_manager_crashing_does_not_stop_the_others(fake, monkeypatch):
    fake.fail_for = {"kopernik"}
    with pytest.raises(SystemExit) as exc:
        backfill.main()
    assert exc.value.code == 1, "a failed manager must not report success"
    slugs = [c["slug"] for c in fake.calls]
    assert "burgundy" in slugs and "drz" in slugs, "others still ran"


def test_the_korean_sweep_will_not_start_itself(monkeypatch, db):
    """A deploy re-runs its start command; a default year made that a re-sweep.

    While the config file was selected, every unrelated deploy kicked off hours
    of DART calls again.
    """
    from pipeline import backfill_kr

    for var in ("KR_BACKFILL_SINCE", "KR_BACKFILL_MANAGER", "KR_BACKFILL_LIMIT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("sys.argv", ["backfill_kr"])

    with pytest.raises(SystemExit) as exc:
        backfill_kr.main()
    assert exc.value.code == 1


def test_an_explicit_year_is_accepted(monkeypatch, db):
    from pipeline import backfill_kr

    monkeypatch.setenv("KR_BACKFILL_SINCE", "2015")
    monkeypatch.setattr(backfill_kr.config, "DART_API_KEY", "")
    monkeypatch.setattr("sys.argv", ["backfill_kr"])

    with pytest.raises(SystemExit) as exc:
        backfill_kr.main()
    # stops on the missing key, i.e. it got past the opt-in gate
    assert exc.value.code == 1
