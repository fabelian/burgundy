"""Parse burgundyasset.com pages.

* ``parse_team``  : team page HTML -> list[PersonnelRow]
* ``parse_aum``   : page HTML/text -> Optional[AumRow]

Both are best-effort and defensive: if the structure is unrecognised they
return an empty result rather than raising, so the collector can still store the
raw document and log a warning (spec §1: "실패 시 raw만 저장하고 경고 로그").
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from collectors.types import AumRow, PersonnelRow

# words that look like a title/role rather than a name
_TITLE_HINT = re.compile(
    r"(chief|officer|president|director|manager|partner|analyst|associate|"
    r"portfolio|founder|chair|head|vice|counsel|principal|cfa|ceo|cio|coo|cfo)",
    re.IGNORECASE,
)


def parse_team(html: str, *, valid_from: Optional[date] = None,
               source: str = "website_team") -> list[PersonnelRow]:
    valid_from = valid_from or date.today()
    soup = BeautifulSoup(html, "lxml")
    people: dict[str, PersonnelRow] = {}

    # Strategy: find containers that carry a person's name in a heading and a
    # role nearby. Works across common CMS team-card layouts.
    candidates = soup.select(
        "[class*=team] , [class*=member] , [class*=bio] , [class*=person] , "
        "[class*=staff] , [class*=profile]"
    )
    for card in candidates:
        name_el = card.find(["h1", "h2", "h3", "h4", "h5"]) or card.find("strong")
        if not name_el:
            continue
        name = _clean(name_el.get_text())
        if not _looks_like_name(name):
            continue
        title = _extract_title(card, name_el)
        if not title:
            continue
        if name not in people:
            people[name] = PersonnelRow(
                person_name=name, title=title, source=source, valid_from=valid_from
            )
    return list(people.values())


def _extract_title(card, name_el) -> str:
    # look at siblings / descendants for the role line
    for el in name_el.find_all_next(["p", "span", "div", "h4", "h5", "em"], limit=4):
        text = _clean(el.get_text())
        if text and _TITLE_HINT.search(text) and not _looks_like_name(text):
            return text
    # class-based hint
    role_el = card.select_one("[class*=title], [class*=role], [class*=position]")
    if role_el:
        text = _clean(role_el.get_text())
        if text:
            return text
    return ""


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


_NAME_PARTICLES = {"de", "la", "le", "van", "von", "der", "den", "di", "da",
                   "du", "of", "the", "el", "al", "bin", "ibn", "st"}


def _looks_like_name(s: str) -> bool:
    if not s or len(s) > 60:
        return False
    if _TITLE_HINT.search(s):
        return False
    words = s.split()
    if not (1 < len(words) <= 6):
        return False
    # first and last word must be capitalised; interior lowercase particles ok
    if not (words[0][:1].isupper() and words[-1][:1].isupper()):
        return False
    for w in words:
        first = w[:1]
        if first.isalpha() and not first.isupper() and w.lower() not in _NAME_PARTICLES:
            return False
    return True


# ---------------------------------------------------------------------------
# AUM
# ---------------------------------------------------------------------------

_AUM_RE = re.compile(
    r"(?:AUM|assets?\s+under\s+management|manage[sd]?)\D{0,40}?"
    r"(C?\$|CAD|USD)?\s*([\d,.]+)\s*(billion|million|bn|mn|b|m)\b",
    re.IGNORECASE,
)
_MULT = {"billion": 1e9, "bn": 1e9, "b": 1e9,
         "million": 1e6, "mn": 1e6, "m": 1e6}


def parse_aum(html: str, *, as_of: Optional[date] = None,
              source: str = "website") -> Optional[AumRow]:
    as_of = as_of or date.today()
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ")
    m = _AUM_RE.search(text)
    if not m:
        return None
    cur_raw, num_raw, mult_raw = m.groups()
    try:
        num = float(num_raw.replace(",", ""))
    except ValueError:
        return None
    amount = num * _MULT.get(mult_raw.lower(), 1)
    currency = "USD" if cur_raw and "US" in cur_raw.upper() else "CAD"
    return AumRow(as_of_date=as_of, aum=round(amount, 2), currency=currency,
                 source=source)
