"""Form ADV / IAPD collector.

Pulls the adviser's regulatory AUM (RAUM, Item 5.F) from the SEC IAPD firm
report and stores it as an ``aum_history`` row with ``source='form_adv'``.
Schedule A owners/executives are reconciled into ``personnel`` when present.

Requires ``FIRM_CRD``; if unset the collector reports "skipped" (no CRD known).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

import config
from collectors.base import BaseCollector, sha256_hex
from collectors.http import sec_get
from collectors.types import AumRow, FetchTarget, PersonnelRow, RawDoc
from pipeline import diff, repo


class FormAdvCollector(BaseCollector):
    source = "form_adv"

    def discover(self) -> list[FetchTarget]:
        if not config.FIRM_CRD:
            print("[form_adv] FIRM_CRD not set; skipping")
            return []
        url = config.IAPD_FIRM_URL.format(crd=config.FIRM_CRD)
        return [FetchTarget(source=self.source, external_id=None, url=url, meta={})]

    def fetch(self, target: FetchTarget) -> Optional[RawDoc]:
        resp = sec_get(target.url)
        payload = resp.text
        return RawDoc(
            source=self.source,
            external_id=None,
            url=target.url,
            payload=payload,
            content_hash=sha256_hex(payload),
        )

    def persist(self, conn, raw_id, raw_payload, target) -> int:
        try:
            data = json.loads(raw_payload)
        except json.JSONDecodeError:
            print("[form_adv] could not decode IAPD JSON; raw stored only")
            return 0

        n = 0
        aum = self._extract_raum(data)
        if aum is not None:
            repo.insert_aum(conn, [aum], raw_id)
            diff.diff_aum(conn, aum.source, aum.as_of_date)
            n += 1

        people = self._extract_schedule_a(data)
        if people:
            diff.reconcile_personnel(conn, "form_adv", people, date.today(), raw_id)
        return n

    # ---- extraction (defensive; IAPD JSON shape varies) -----------------
    def _extract_raum(self, data: dict) -> Optional[AumRow]:
        # IAPD search results nest the firm hit under hits.hits[].._source
        hit = self._first_hit(data)
        if not hit:
            return None
        raum = None
        for key in ("raum", "totalRAUM", "aum", "totalAmount"):
            if key in hit and hit[key]:
                raum = hit[key]
                break
        if raum is None:
            return None
        try:
            amount = float(str(raum).replace(",", "").replace("$", ""))
        except ValueError:
            return None
        return AumRow(as_of_date=date.today(), aum=amount,
                     currency="USD", source="form_adv")

    def _extract_schedule_a(self, data: dict) -> list[PersonnelRow]:
        hit = self._first_hit(data)
        if not hit:
            return []
        owners = hit.get("scheduleA") or hit.get("owners") or []
        rows: list[PersonnelRow] = []
        for o in owners if isinstance(owners, list) else []:
            name = o.get("name") or o.get("fullName")
            title = o.get("title") or o.get("titleOrStatus") or "Owner/Executive"
            if name:
                rows.append(PersonnelRow(person_name=str(name).strip(),
                                         title=str(title).strip(),
                                         source="form_adv",
                                         valid_from=date.today()))
        return rows

    @staticmethod
    def _first_hit(data: dict) -> Optional[dict]:
        try:
            hits = data.get("hits", {}).get("hits", [])
            if hits:
                return hits[0].get("_source", hits[0])
        except AttributeError:
            pass
        return data if isinstance(data, dict) else None
