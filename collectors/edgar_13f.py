"""EDGAR 13F-HR collector.

discover: submissions JSON -> list of 13F-HR / 13F-HR/A filings
fetch:    locate + download the information-table XML for a filing
persist:  parse_13f -> holdings insert -> diff_us_holdings
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterator, Optional

from dateutil import parser as dateparse

import config
from collectors.base import BaseCollector, sha256_hex
from collectors.http import sec_get
from collectors.types import FetchTarget, RawDoc
from parsers.parse_13f import parse_13f
from pipeline import diff, repo

FORMS_13F = {"13F-HR", "13F-HR/A"}


def _to_date(s: str) -> date:
    return dateparse.parse(s).date()


class Edgar13FCollector(BaseCollector):
    source = "edgar_13f"

    def __init__(self, *, since: Optional[date] = None, limit: Optional[int] = None):
        self.since = since          # backfill floor on reportDate
        self.limit = limit          # cap number of filings (backfill batching)

    # ---- discover -------------------------------------------------------
    def discover(self) -> list[FetchTarget]:
        subs = sec_get(config.SEC_SUBMISSIONS_URL).json()
        targets: list[FetchTarget] = []
        for f in self._iter_filings(subs):
            if f["form"] not in FORMS_13F:
                continue
            report_date = _to_date(f["reportDate"]) if f.get("reportDate") else None
            if self.since and report_date and report_date < self.since:
                continue
            targets.append(
                FetchTarget(
                    source=self.source,
                    external_id=f["accessionNumber"],
                    url=self._filing_dir(f["accessionNumber"]),
                    meta={
                        "form": f["form"],
                        "filing_date": f["filingDate"],
                        "report_date": f.get("reportDate"),
                        "is_amendment": f["form"].endswith("/A"),
                    },
                )
            )
        # newest first; backfill limit applied after sort
        targets.sort(key=lambda t: t.meta.get("report_date") or "", reverse=True)
        if self.limit:
            targets = targets[: self.limit]
        return targets

    def _iter_filings(self, subs: dict) -> Iterator[dict]:
        recent = subs.get("filings", {}).get("recent", {})
        yield from self._zip_arrays(recent)
        # older filings live in additional JSON files
        for extra in subs.get("filings", {}).get("files", []):
            name = extra.get("name")
            if not name:
                continue
            url = f"https://data.sec.gov/submissions/{name}"
            try:
                data = sec_get(url).json()
            except Exception as exc:  # pragma: no cover - network
                print(f"[edgar_13f] could not load {url}: {exc}")
                continue
            yield from self._zip_arrays(data)

    @staticmethod
    def _zip_arrays(block: dict) -> Iterator[dict]:
        forms = block.get("form")
        if not forms:
            return
        keys = ["accessionNumber", "filingDate", "reportDate", "form",
                "primaryDocument"]
        for i in range(len(forms)):
            yield {k: (block.get(k) or [None] * len(forms))[i] for k in keys}

    def _filing_dir(self, accession_no: str) -> str:
        acc_nodash = accession_no.replace("-", "")
        return f"{config.SEC_ARCHIVES_BASE}/{config.CIK_INT}/{acc_nodash}/"

    # ---- fetch ----------------------------------------------------------
    def fetch(self, target: FetchTarget) -> Optional[RawDoc]:
        xml = self._find_info_table_xml(target.url)
        if xml is None:
            print(f"[edgar_13f] no info table found for {target.external_id}")
            return None
        return RawDoc(
            source=self.source,
            external_id=target.external_id,
            url=target.url,
            payload=xml,
            content_hash=sha256_hex(xml),
            meta=target.meta,
        )

    def _find_info_table_xml(self, filing_dir: str) -> Optional[str]:
        index = sec_get(filing_dir + "index.json").json()
        items = index.get("directory", {}).get("item", [])
        xml_files = [it["name"] for it in items
                     if it.get("name", "").lower().endswith(".xml")]
        # deprioritise the cover-page primary_doc.xml
        xml_files.sort(key=lambda n: ("primary_doc" in n.lower(),
                                      "info" not in n.lower()
                                      and "table" not in n.lower()))
        for name in xml_files:
            try:
                text = sec_get(filing_dir + name).text
            except Exception:
                continue
            if "infoTable" in text or "informationTable" in text:
                return text
        return None

    # ---- persist --------------------------------------------------------
    def persist(self, conn, raw_id, raw_payload, target) -> int:
        meta = target.meta
        report_date = _to_date(meta["report_date"]) if meta.get("report_date") else date.today()
        filing_date = _to_date(meta["filing_date"]) if meta.get("filing_date") else date.today()
        rows = parse_13f(
            raw_payload,
            as_of_date=report_date,
            filed_at=filing_date,
            accession_no=target.external_id,
            is_amendment=bool(meta.get("is_amendment")),
        )
        n = repo.insert_holdings(conn, rows, raw_id)
        diff.diff_us_holdings(conn, target.external_id)
        return n
