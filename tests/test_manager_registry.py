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


def test_kopernik_still_has_no_identifiers_to_collect_with():
    entry = _entry("kopernik")
    assert entry.get("legal_name"), "identity is confirmed"
    for field in ("cik", "crd", "website_aum_url", "website_team_url"):
        assert entry.get(field) is None, f"kopernik.{field} was guessed"


def test_no_website_url_was_inferred_from_a_confirmed_firm_name():
    """Knowing the firm does not supply its URLs either. A wrong one scrapes
    somebody else's team page under this manager's name."""
    for slug in ("drz", "kopernik"):
        entry = _entry(slug)
        assert entry.get("website_aum_url") is None
        assert entry.get("website_team_url") is None


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


def test_the_confirmed_managers_still_collect(db):
    """The blanks must not have loosened anything for the managers whose
    identifiers *were* read off their own filings."""
    managers.sync_from_config(db)
    tracked = {m["slug"]: m for m in managers.active(db)}

    for slug in ("burgundy", "mawer", "edgepoint", "beutel-goodman",
                 "letko-brosseau"):
        assert Edgar13FCollector(tracked[slug]).applies() is True, slug


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
