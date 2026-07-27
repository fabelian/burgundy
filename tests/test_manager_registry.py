"""The manager registry, and identifiers that arrive one at a time.

A CIK is an identity, not a detail: the wrong ten digits fill the dashboard
with another firm's portfolio and nothing downstream looks wrong. So a manager
is tracked as soon as it is named, each identifier is filled in only when
supplied, and the consequence of a blank has to be the safe one — the
collector that needs it skips, visibly, rather than running against a guess.

Knowing *which firm* a manager is does not supply any of them: there is no
name-to-CIK resolution here, and a confirmed legal name must not be enough to
start collecting.
"""
from __future__ import annotations

import config
from collectors.edgar_13f import Edgar13FCollector
from collectors.form_adv import FormAdvCollector
from collectors.website import WebsiteTeamCollector
from pipeline import managers


def _entry(slug: str) -> dict:
    return next(m for m in config.MANAGERS if m["slug"] == slug)


def test_the_new_managers_are_tracked(db):
    managers.sync_from_config(db)
    slugs = {m["slug"] for m in managers.active(db)}
    assert {"drz", "kopernik"} <= slugs


def test_a_manager_without_a_cik_is_skipped_rather_than_guessed_at(db):
    """The invariant, not a list: whichever managers are still missing a CIK,
    EDGAR must pass over them. There is no name-to-CIK resolution here, so a
    confirmed legal name must never be enough to start collecting — a wrong
    CIK shows another firm's portfolio and looks entirely normal downstream."""
    managers.sync_from_config(db)
    tracked = {m["slug"]: m for m in managers.active(db)}

    for entry in config.MANAGERS:
        if entry.get("cik"):
            continue
        manager = tracked[entry["slug"]]
        assert Edgar13FCollector(manager).applies() is False, entry["slug"]


def test_a_manager_without_a_crd_is_skipped_by_form_adv(db):
    managers.sync_from_config(db)
    tracked = {m["slug"]: m for m in managers.active(db)}

    for entry in config.MANAGERS:
        if entry.get("crd"):
            continue
        assert FormAdvCollector(tracked[entry["slug"]]).applies() is False


def test_every_cik_is_ten_digits_and_unique():
    """``managers`` has UNIQUE (cik), so a duplicate would be rejected at sync
    — but by then the wrong manager may already own the number. Padding
    matters less (the collector zero-fills) yet an odd length is a good sign
    that something other than a CIK was pasted in."""
    ciks = [m["cik"] for m in config.MANAGERS if m.get("cik")]

    assert len(ciks) == len(set(ciks)), "two managers share a CIK"
    for cik in ciks:
        assert cik.isdigit() and len(cik) == 10, cik


def test_drz_collects_from_edgar_now_that_its_cik_is_known(db):
    managers.sync_from_config(db)
    drz = next(m for m in managers.active(db) if m["slug"] == "drz")

    assert drz["cik"] == "0001008894"
    assert Edgar13FCollector(drz).applies() is True


def test_kopernik_collects_from_edgar_now_that_its_cik_is_known(db):
    managers.sync_from_config(db)
    kopernik = next(m for m in managers.active(db) if m["slug"] == "kopernik")

    assert kopernik["cik"] == "0001599814"
    assert Edgar13FCollector(kopernik).applies() is True


def test_no_url_path_was_invented_beyond_the_domain_that_was_given():
    """A supplied domain is not a supplied page. Guessing a team-page path
    scrapes whatever happens to sit there and files those people under this
    manager, which reads exactly like a real personnel record."""
    assert _entry("kopernik")["website_aum_url"] == "https://www.kopernikglobal.com/"
    assert _entry("kopernik")["website_team_url"] is None
    assert _entry("drz")["website_aum_url"] is None
    assert _entry("drz")["website_team_url"] is None


def test_a_manager_without_a_team_url_is_skipped_by_that_scrape(db):
    managers.sync_from_config(db)
    tracked = {m["slug"]: m for m in managers.active(db)}

    for entry in config.MANAGERS:
        if entry.get("website_team_url"):
            continue
        assert WebsiteTeamCollector(tracked[entry["slug"]]).applies() is False


def test_dart_terms_match_the_reporter_without_catching_bystanders():
    """The DART parser matches reporter names by case-insensitive substring, so
    a short term is a liability. "DRZ" is three letters and appears inside
    unrelated names, which would file someone else's stake under this manager."""
    from parsers.parse_dart import _reporter_matches

    terms = {m["slug"]: m.get("dart_terms") or [] for m in config.MANAGERS}

    assert _reporter_matches("DEPRINCE RACE & ZOLLO INC", terms["drz"])
    assert _reporter_matches("KOPERNIK GLOBAL INVESTORS LLC", terms["kopernik"])

    assert not _reporter_matches("ANDRZEJ HOLDINGS", terms["drz"])
    assert _reporter_matches("ANDRZEJ HOLDINGS", ["DRZ"]), (
        "the hazard is real, which is why 'DRZ' is not one of the terms")
    assert not _reporter_matches("Kopernik Global Investors LLC", terms["drz"])
    assert not _reporter_matches("Burgundy Asset Management", terms["kopernik"])


def test_no_dart_term_is_short_enough_to_match_by_accident():
    for m in config.MANAGERS:
        for term in m.get("dart_terms") or []:
            if term.isascii():
                assert len(term) >= 5, f"{m['slug']}: {term!r} is too short"


# ---- retiring a manager --------------------------------------------------

_RETIRED = ("mawer", "edgepoint", "beutel-goodman", "letko-brosseau")


def test_a_retired_manager_is_neither_collected_nor_served(db):
    """One flag has to do both jobs. pipeline.run iterates active(), and every
    dashboard tab resolves through it, so is_active=False stops outbound
    collection *and* takes the manager off the web app."""
    managers.sync_from_config(db)
    live = {m["slug"] for m in managers.active(db)}

    assert live == {"burgundy", "drz", "kopernik"}
    for slug in _RETIRED:
        assert slug not in live, slug


def test_a_retired_manager_cannot_be_reached_by_url(db):
    """The picker hiding them is not enough — a hand-typed ?manager= slug must
    not serve their data either."""
    from dashboard import queries

    managers.sync_from_config(db)
    db.commit()  # queries.* open their own connection

    for slug in _RETIRED:
        resolved = queries.manager_by_slug(slug)
        assert resolved is not None, "an unknown slug still falls back"
        assert resolved["slug"] != slug, f"{slug} was served directly"

    assert {m["slug"] for m in queries.manager_list()} == {
        "burgundy", "drz", "kopernik"}


def test_retiring_keeps_the_data_it_collected(db):
    """Deactivation is reversible; that is the whole reason to prefer it over
    deleting. The rows have to still be there."""
    managers.sync_from_config(db)
    row = db.execute(
        "SELECT id FROM managers WHERE slug = 'mawer'").fetchone()
    assert row is not None, "the manager row survives deactivation"


def test_config_can_switch_a_manager_back_on(db, monkeypatch):
    """is_active is deliberately not COALESCEd on upsert: a flag that only ever
    turns on could never retire anyone, and one that only ever turns off could
    never bring them back."""
    managers.sync_from_config(db)
    assert "mawer" not in {m["slug"] for m in managers.active(db)}

    revived = [{**m, "is_active": True} if m["slug"] == "mawer" else m
               for m in config.MANAGERS]
    monkeypatch.setattr(config, "MANAGERS", revived)
    managers.sync_from_config(db)

    assert "mawer" in {m["slug"] for m in managers.active(db)}


def test_a_manager_with_no_is_active_key_defaults_to_tracked():
    """Every entry predating the flag must keep collecting."""
    assert config.MANAGERS[0].get("is_active", True) is True


def test_every_tracked_manager_with_a_cik_still_collects(db):
    """The blanks and the retirements must not have loosened anything for the
    managers that are still tracked and do have identifiers."""
    managers.sync_from_config(db)
    tracked = managers.active(db)

    assert tracked, "something is tracked"
    for m in tracked:
        if m["cik"]:
            assert Edgar13FCollector(m).applies() is True, m["slug"]


def test_every_manager_has_a_unique_slug_and_sort_order():
    slugs = [m["slug"] for m in config.MANAGERS]
    orders = [m.get("sort_order", 100) for m in config.MANAGERS]
    assert len(slugs) == len(set(slugs))
    assert len(orders) == len(set(orders)), "a tie makes the picker order vary"


def test_managers_without_a_cik_do_not_collide_on_the_unique_index(db):
    """``managers`` has UNIQUE (cik). Every manager still awaiting one carries
    NULL, and NULLs must not compare equal or the second would be rejected."""
    managers.sync_from_config(db)
    written = managers.sync_from_config(db)          # idempotent re-run
    assert written == len(config.MANAGERS)

    blank = db.execute(
        "SELECT count(*) c FROM managers WHERE cik IS NULL").fetchone()["c"]
    assert blank == sum(1 for m in config.MANAGERS if not m.get("cik"))
