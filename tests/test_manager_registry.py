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


def test_an_unconfirmed_manager_carries_no_invented_identifiers():
    """The identifiers below could not be read off the filer's own documents
    from here, so none of them may be present. A guessed CIK is the failure
    this asserts against — it would not look wrong anywhere downstream."""
    for slug in _UNCONFIRMED:
        entry = next(m for m in config.MANAGERS if m["slug"] == slug)
        for field in ("cik", "crd", "legal_name",
                      "website_aum_url", "website_team_url"):
            assert entry.get(field) is None, f"{slug}.{field} was guessed"


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
