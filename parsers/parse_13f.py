"""Parse a 13F-HR information table XML into HoldingRow list.

Pure function: raw XML payload -> list[HoldingRow]. No DB, no network.

The 13F information table is namespaced XML. Namespaces vary between filings
(``eis``, ``ns1``, default, ...) so we match on local tag names rather than a
fixed namespace URI.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from lxml import etree

from collectors.types import AumRow, HoldingRow

# SEC changed the 13F "value" unit from USD-thousands to whole USD. The rule
# keys off when the report was *filed*, not the period it covers: everything
# filed on/after 2023-01-03 reports whole dollars. Q4-2022 is the case that
# makes the difference — its period is in 2022 but it is filed in early 2023,
# so it already reports whole dollars and must not be scaled.
_WHOLE_DOLLARS_FILED_FROM = date(2023, 1, 3)


def _localname(tag: str) -> str:
    """Strip the namespace from a qualified tag name."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_child(el, name: str):
    for child in el:
        if _localname(child.tag) == name:
            return child
    return None


def _find_text(el, name: str) -> Optional[str]:
    child = _find_child(el, name)
    if child is None:
        return None
    text = (child.text or "").strip()
    return text or None


def parse_13f(
    payload: str | bytes,
    *,
    as_of_date: date,
    filed_at: date,
    accession_no: str,
    is_amendment: bool = False,
) -> list[HoldingRow]:
    """Parse an information-table XML document.

    ``payload`` is the raw XML text of the information table document. The
    quarter-end/filing metadata comes from the caller (the submissions index),
    not the XML, because the info-table itself does not carry it.
    """
    if isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = payload

    # recover=True tolerates the occasional malformed SEC XML.
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True)
    root = etree.fromstring(data, parser=parser)
    if root is None:
        return []

    rows: list[HoldingRow] = []
    for el in root.iter():
        if _localname(el.tag) != "infoTable":
            continue

        name = _find_text(el, "nameOfIssuer") or ""
        cusip = _find_text(el, "cusip") or ""
        if not cusip:
            continue
        cusip = cusip.upper()

        value_raw = _find_text(el, "value")
        # 13F value historically in USD thousands; some post-2023 filings switch
        # to whole dollars but the tag stays "value". We store as reported.
        value_kusd = int(round(float(value_raw))) if value_raw else 0

        shares = 0
        shrs_or_prn = _find_child(el, "shrsOrPrnAmt")
        if shrs_or_prn is not None:
            sh = _find_text(shrs_or_prn, "sshPrnamt")
            if sh:
                shares = int(round(float(sh)))

        rows.append(
            HoldingRow(
                as_of_date=as_of_date,
                filed_at=filed_at,
                accession_no=accession_no,
                is_amendment=is_amendment,
                cusip=cusip,
                name=name,
                shares=shares,
                value_kusd=value_kusd,
                ticker=None,
            )
        )

    _assign_weights(rows)
    return rows


def parse_cover(payload: str | bytes) -> dict:
    """Extract report type and 'other managers' from a 13F primary_doc.xml.

    Used for 13F-NT (Notice) filings, whose cover page names the manager(s)
    reporting the holdings on this filer's behalf (e.g. an acquirer). Returns
    ``{"report_type": str|None, "other_managers": str|None}`` — best effort,
    tolerant of namespace variation.
    """
    if isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = payload
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True)
    root = etree.fromstring(data, parser=parser)
    if root is None:
        return {"report_type": None, "other_managers": None}

    report_type = None
    names: list[str] = []
    for el in root.iter():
        tag = _localname(el.tag)
        if tag == "reportType" and el.text:
            report_type = el.text.strip()
        # a <name> is an "other manager" name if any ancestor tag mentions it
        if tag == "name" and el.text and el.text.strip():
            if any("othermanager" in _localname(a.tag).lower()
                   for a in el.iterancestors()):
                names.append(el.text.strip())

    # de-dupe while preserving order
    seen: set[str] = set()
    uniq = [n for n in names if not (n in seen or seen.add(n))]
    other = "; ".join(uniq) if uniq else None
    return {"report_type": report_type, "other_managers": other}


def compute_total_aum(rows: list[HoldingRow], as_of: date,
                      filed_at: date) -> AumRow | None:
    """Derive an approximate AUM figure from a 13F filing (US long positions).

    Stored as ``source='13f_total'`` in whole USD. Returns None for an empty
    filing. ``filed_at`` — not ``as_of`` — decides the unit: the SEC's switch to
    whole dollars applies to reports *filed* from 2023-01-03 onwards.
    """
    if not rows:
        return None
    total_reported = sum(r.value_kusd for r in rows)
    multiplier = 1000 if filed_at < _WHOLE_DOLLARS_FILED_FROM else 1
    return AumRow(
        as_of_date=as_of,
        aum=float(total_reported * multiplier),
        currency="USD",
        source="13f_total",
    )


def _assign_weights(rows: list[HoldingRow]) -> None:
    """Fill ``weight`` as each position's share of total portfolio value."""
    total = sum(r.value_kusd for r in rows)
    if total <= 0:
        return
    for r in rows:
        r.weight = round(r.value_kusd / total, 5)
