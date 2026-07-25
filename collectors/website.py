"""Company-website collectors: AUM figure + team page.

Two collectors share this module:
  * WebsiteAumCollector  (source='website_aum')  -> aum_history source='website'
  * WebsiteTeamCollector (source='website_team') -> personnel SCD2

Both are resilient: if parsing yields nothing, the raw HTML is still stored and
a warning is logged (spec §1).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import config
from collectors.base import BaseCollector, sha256_hex
from collectors.http import get_text
from collectors.types import FetchTarget, RawDoc
from parsers.parse_website import parse_aum, parse_team
from pipeline import diff, repo


class WebsiteAumCollector(BaseCollector):
    source = "website_aum"

    def applies(self) -> bool:
        return bool(self.manager.get("website_aum_url"))

    def discover(self) -> list[FetchTarget]:
        if not self.manager.get("website_aum_url"):
            return []
        return [FetchTarget(source=self.source, external_id=None,
                            url=self.manager["website_aum_url"], meta={})]

    def fetch(self, target: FetchTarget) -> Optional[RawDoc]:
        html = get_text(target.url)
        return RawDoc(source=self.source, external_id=None, url=target.url,
                     payload=html, content_hash=sha256_hex(html))

    def persist(self, conn, raw_id, raw_payload, target) -> int:
        aum = parse_aum(raw_payload, as_of=date.today(), source="website")
        if aum is None:
            print("[website_aum] no AUM figure found; raw stored only")
            return 0
        n = repo.insert_aum(conn, self.manager_id, [aum], raw_id)
        diff.diff_aum(conn, self.manager_id, "website", aum.as_of_date)
        return n

    def already_have_target(self, conn, target: FetchTarget) -> bool:
        return False


class WebsiteTeamCollector(BaseCollector):
    source = "website_team"

    def applies(self) -> bool:
        return bool(self.manager.get("website_team_url"))

    def discover(self) -> list[FetchTarget]:
        if not self.manager.get("website_team_url"):
            return []
        return [FetchTarget(source=self.source, external_id=None,
                            url=self.manager["website_team_url"], meta={})]

    def fetch(self, target: FetchTarget) -> Optional[RawDoc]:
        html = get_text(target.url)
        return RawDoc(source=self.source, external_id=None, url=target.url,
                     payload=html, content_hash=sha256_hex(html))

    def persist(self, conn, raw_id, raw_payload, target) -> int:
        people = parse_team(raw_payload, valid_from=date.today(),
                            source="website_team")
        if not people:
            print("[website_team] no personnel parsed; raw stored only")
            return 0
        # SCD2 reconcile handles inserts + diffs; returns event count.
        diff.reconcile_personnel(conn, self.manager_id, "website_team", people,
                                 date.today(), raw_id)
        return len(people)

    def already_have_target(self, conn, target: FetchTarget) -> bool:
        return False
