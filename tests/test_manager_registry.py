"""Registering a manager whose identifiers have not been confirmed.

A CIK is an identity, not a detail: the wrong ten digits fill the dashboard
with another firm's portfolio and nothing downstream looks wrong. So a manager
can be tracked before its identifiers are known, and the consequence of the
blank has to be the safe one — collectors skip it, loudly, rather than run
against a guess.
"""
from __future__ import annotations

import config
from collectors.dart_5pct import Dart5pctCollector
from collectors.edgar_13f import Edgar13FCollector
from collectors.form_adv import FormAdvCollector
from collectors.website import WebsiteAumCollector, WebsiteTeamCollector
from pipeline import managers

_UNCONFIRMED = ("drz", "kopernik")


def test_the_new_managers_are_tracked(db):
    managers.sync_from_config(db)
    slugs = {m["slug"] for m in managers.active(db)}
    assert _UNCONFIRMED[0] in slugs and _UNCONFIRMED[1] in slugs


def test_knowing_which_firm_it_is_does_not_supply_its_identifiers():
    """Firm identity and filing identifiers are separate facts, and confirming
    the first does not confirm the second. There is no name-to-CIK resolution
    in this repo — Edgar13FCollector.applies() requires the number — so a
    legal name filled in from a confirmation must not drag a guessed CIK with
    it. A wrong CIK is the failure being guarded: it looks entirely normal
    downstream while showing another firm's portfolio."""
    for slug in _UNCONFIRMED:
        entry = next(m for m in config.MANAGERS if m["slug"] == slug)
        assert entry.get("legal_name"), f"{slug} identity is confirmed"
        for field in ("cik", "crd", "website_aum_url", "website_team_url"):
            assert entry.get(field) is None, f"{slug}.{field} was guessed"


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


def test_an_unconfirmed_manager_is_skipped_rather_than_collected(db):
    """Skipping is recorded on the collector panel as "not configured", which
    is a visible prompt to go and confirm the identifiers — unlike a silent
    empty result, which reads as a manager that files nothing."""
    managers.sync_from_config(db)
    tracked = {m["slug"]: m for m in managers.active(db)}

    for slug in _UNCONFIRMED:
        manager = tracked[slug]
        for cls in (Edgar13FCollector, FormAdvCollector, Dart5pctCollector,
                    WebsiteAumCollector, WebsiteTeamCollector):
            assert cls(manager).applies() is False, f"{slug}/{cls.source}"


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
    """``managers`` has UNIQUE (cik). Two unconfirmed managers both carry NULL,
    and NULLs must not be treated as equal or the second one would be rejected."""
    managers.sync_from_config(db)
    written = managers.sync_from_config(db)          # idempotent re-run
    assert written == len(config.MANAGERS)

    blank = db.execute(
        "SELECT count(*) c FROM managers WHERE cik IS NULL").fetchone()["c"]
    assert blank == len(_UNCONFIRMED)
