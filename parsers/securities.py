"""Identify a security named only by a printed string.

A fact sheet gives a name and, if you are lucky, a country column. There is no
CUSIP and rarely an ISIN, so two jobs fall here:

* ``security_key`` — a stable key for the same position across documents, so
  re-fetching a fact sheet updates a row instead of duplicating it.
* ``is_korean`` — whether the position is what the Korea tab is looking for.

Both are deliberately conservative. A name-matching rule that reaches too far
would put another country's company on the Korea tab, and a wrong holding shown
to a prospect is worse than a missing one.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Legal-form suffixes carry no identity: "Samsung Electronics Co., Ltd." and
# "Samsung Electronics" are the same position, printed by two documents.
_SUFFIXES = (
    "co ltd", "co limited", "company limited", "holdings ltd", "ltd", "limited",
    "inc", "incorporated", "corp", "corporation", "plc", "nv", "n v", "sa",
    "s a", "ag", "se", "spa", "s p a", "ab", "asa", "oyj", "kk", "k k",
    "pte", "llc", "lp", "gmbh", "holdings", "holding", "group", "the",
)

# Share-class markers, likewise. Mawer prints "Samsung Electronics Co Ltd Pref"
# for the preferred line; it is still Samsung Electronics for our purposes, but
# it is a *different position*, so the class is kept in the key rather than
# stripped — see ``_CLASS_MARKERS`` handling below.
_CLASS_MARKERS = {
    "pref": "pref", "preferred": "pref", "pfd": "pref",
    "adr": "adr", "ads": "adr", "gdr": "gdr",
}

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")


def security_key(name: str, *, ticker: Optional[str] = None,
                 isin: Optional[str] = None) -> str:
    """A stable identity for a named position.

    An ISIN is a real identifier, so it wins outright when present. Otherwise
    the printed name is normalised: unicode-folded, stripped of punctuation and
    legal-form suffixes, lowercased. A share class (pref/ADR/GDR) is preserved,
    because a preferred line is a separate position that a fund can hold
    alongside the common one.
    """
    if isin and isin.strip():
        return f"isin:{isin.strip().upper()}"

    text = unicodedata.normalize("NFKC", name or "").strip()
    text = _PUNCT.sub(" ", text)
    text = _SPACE.sub(" ", text).strip().lower()

    words = text.split()
    classes: list[str] = []
    while words and words[-1] in _CLASS_MARKERS:
        classes.insert(0, _CLASS_MARKERS[words.pop()])

    # Strip trailing legal-form suffixes, longest match first so "co ltd" goes
    # before "ltd" and does not leave a stray "co" behind.
    changed = True
    while changed and words:
        changed = False
        for suffix in sorted(_SUFFIXES, key=lambda s: -len(s.split())):
            parts = suffix.split()
            if len(words) > len(parts) and words[-len(parts):] == parts:
                del words[-len(parts):]
                changed = True
                break

    core = " ".join(words)
    if not core:
        # A name that is nothing but suffixes is not something to guess at;
        # fall back to the normalised original so the row stays distinguishable.
        core = text
    if classes:
        core = f"{core} {' '.join(classes)}"
    if not core and ticker:
        return f"ticker:{ticker.strip().upper()}"
    return core


# ---------------------------------------------------------------------------
# Korean identification
# ---------------------------------------------------------------------------

# Hangul syllables and jamo. A Korean-script name is Korean beyond argument.
_HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")

# Country spellings seen in fund documents, plus the codes.
_KOREAN_COUNTRIES = {
    "kr", "kor", "korea", "south korea", "korea south", "s korea",
    "republic of korea", "korea republic of", "the republic of korea",
    "대한민국", "한국", "남한",
}

# Deliberately not "any company that happens to be Korean": these are the names
# that make the tab worth opening — the large caps an institutional desk can
# actually write research on. Used only when the document prints no country
# column.
#
# Written as they are printed and run through ``security_key`` at import, so an
# entry can never drift out of the form the lookup actually uses.
_KOREAN_LARGE_CAP_NAMES = (
    "Samsung Electronics Co Ltd", "Samsung SDI Co Ltd",
    "Samsung Biologics Co Ltd", "Samsung C&T Corp",
    "Samsung Life Insurance Co Ltd", "Samsung Fire & Marine Insurance Co Ltd",
    "Samsung Heavy Industries Co Ltd", "Samsung Electro-Mechanics Co Ltd",
    "Samsung SDS Co Ltd",
    "SK Hynix Inc", "SK Telecom Co Ltd", "SK Innovation Co Ltd",
    "SK Square Co Ltd", "SK Inc",
    "LG Chem Ltd", "LG Electronics Inc", "LG Energy Solution Ltd",
    "LG H&H Co Ltd", "LG Household & Health Care Ltd", "LG Display Co Ltd",
    "LG Uplus Corp",
    "NAVER Corp", "Kakao Corp", "KakaoBank Corp", "KakaoPay Corp",
    "Hyundai Motor Co", "Hyundai Mobis Co Ltd", "Hyundai Steel Co",
    "Hyundai Heavy Industries Co Ltd", "Kia Corp",
    "POSCO Holdings Inc", "POSCO International Corp",
    "Celltrion Inc", "Korea Electric Power Corp", "KEPCO",
    "KB Financial Group Inc", "Shinhan Financial Group Co Ltd",
    "Hana Financial Group Inc", "Woori Financial Group Inc",
    "Industrial Bank of Korea", "Korea Investment Holdings Co Ltd",
    "KT Corp", "KT&G Corp", "AmorePacific Corp", "Coway Co Ltd",
    "Hanwha Corp", "Hanwha Aerospace Co Ltd", "Hanwha Solutions Corp",
    "HMM Co Ltd", "Doosan Corp", "Doosan Enerbility Co Ltd",
    "HD Hyundai Co Ltd", "HYBE Co Ltd", "Krafton Inc",
    "Ecopro Co Ltd", "Ecopro BM Co Ltd", "Hanmi Pharm Co Ltd",
    "Yuhan Corp", "Lotte Chemical Corp", "Shinsegae Co Ltd",
    "CJ CheilJedang Corp", "CJ Corp", "S-Oil Corp", "Korean Air Lines Co Ltd",
    "Hanjin KAL Corp", "Mirae Asset Securities Co Ltd",
    "Hankook Tire & Technology Co Ltd", "Hanon Systems", "Orion Corp",
)

_KOREAN_LARGE_CAPS = frozenset(security_key(n) for n in _KOREAN_LARGE_CAP_NAMES)

_CLASS_SUFFIXES = tuple(f" {c}" for c in sorted(set(_CLASS_MARKERS.values())))


def _without_class(key: str) -> str:
    """Drop a trailing share-class marker from a key.

    The preferred line of a Korean large cap is a different *position* but the
    same *country*, so the class stays in the identity key while the Korean
    lookup ignores it. Without this, "Samsung Electronics Co Ltd Pref" — a
    holding these funds genuinely carry — would not read as Korean.
    """
    for suffix in _CLASS_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)]
    return key


def normalize_country(country: Optional[str]) -> Optional[str]:
    """Lowercase, punctuation-free country text for comparison."""
    if not country:
        return None
    text = unicodedata.normalize("NFKC", country).strip()
    text = _PUNCT.sub(" ", text)
    text = _SPACE.sub(" ", text).strip().lower()
    return text or None


def is_korean(*, country: Optional[str] = None, name: Optional[str] = None,
              ticker: Optional[str] = None, isin: Optional[str] = None) -> bool:
    """Whether a disclosed position is a Korean security.

    The document's own country column decides when there is one — including
    deciding *against*, so a fund that lists "Samsung Electronics / Taiwan" is
    taken at its word rather than overridden by a name list.

    With no country column the fallbacks are, in order: an ISIN beginning KR,
    a Korean-script name, a ticker in KRX six-digit form, and finally the
    large-cap name list. The name list is a floor, not a census: a Korean small
    cap absent from it reads as not-Korean, which is the safe direction for a
    tab whose purpose is large caps.
    """
    normalized_country = normalize_country(country)
    if normalized_country:
        return normalized_country in _KOREAN_COUNTRIES

    if isin and isin.strip().upper().startswith("KR"):
        return True

    if name and _HANGUL.search(name):
        return True

    # KRX codes are six digits. A bare six-digit ticker on an international
    # fund's sheet is a Korean listing; anything with letters is not.
    if ticker:
        bare = ticker.strip().upper().removesuffix(".KS").removesuffix(".KQ")
        if re.fullmatch(r"\d{6}", bare):
            return True

    if name:
        return _without_class(security_key(name)) in _KOREAN_LARGE_CAPS
    return False
