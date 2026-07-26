"""Identifying a security that a fact sheet names only in print.

Two failure modes matter and they are not symmetric. A missed Korean name
leaves a real position off the tab; a false positive puts another country's
company in front of a prospect as a Korean holding. The second is worse, so the
rules here are asked to prove they stay narrow.
"""
from __future__ import annotations

from parsers.securities import is_korean, security_key


# ---- security_key --------------------------------------------------------

def test_same_company_printed_differently_gets_one_key():
    """A re-fetch must update the position, not duplicate it."""
    assert (security_key("Samsung Electronics Co., Ltd.")
            == security_key("SAMSUNG ELECTRONICS CO LTD")
            == security_key("Samsung Electronics"))


def test_legal_suffixes_are_stripped_to_the_core_name():
    assert security_key("POSCO Holdings Inc.") == "posco"
    assert security_key("Nestle S.A.") == "nestle"
    assert security_key("Roche Holding AG") == "roche"


def test_preferred_line_is_a_separate_position():
    """A fund can hold the common and the preferred at once; they are not one
    row, so the class stays in the key."""
    assert (security_key("Samsung Electronics Co Ltd Pref")
            != security_key("Samsung Electronics Co Ltd"))
    assert security_key("Samsung Electronics Co Ltd Pref").endswith("pref")


def test_isin_wins_when_present():
    assert security_key("whatever", isin="KR7005930003") == "isin:KR7005930003"


def test_a_name_that_is_only_a_suffix_still_yields_a_key():
    assert security_key("Holdings Ltd") != ""


# ---- is_korean -----------------------------------------------------------

def test_document_country_column_decides():
    assert is_korean(country="South Korea", name="Anything")
    assert is_korean(country="Korea, Republic of", name="Anything")
    assert is_korean(country="KR", name="Anything")


def test_document_country_also_decides_against():
    """A name list must never overrule what the document actually printed."""
    assert not is_korean(country="Taiwan", name="Samsung Electronics")
    assert not is_korean(country="United States", name="SK Hynix Inc")


def test_large_caps_are_found_without_a_country_column():
    for name in ("Samsung Electronics Co., Ltd.", "SK Hynix Inc.",
                 "NAVER Corp", "POSCO Holdings Inc.", "Kia Corp",
                 "KB Financial Group Inc"):
        assert is_korean(name=name), name


def test_preferred_line_of_a_large_cap_is_still_korean():
    """These funds do hold the preferred line; a share class does not move a
    company to another country."""
    assert is_korean(name="Samsung Electronics Co Ltd Pref")


def test_korean_script_name_is_korean():
    assert is_korean(name="삼성전자")


def test_isin_and_krx_ticker_are_korean():
    assert is_korean(name="Unlisted Name", isin="KR7005930003")
    assert is_korean(name="Unlisted Name", ticker="005930")
    assert is_korean(name="Unlisted Name", ticker="005930.KS")


def test_non_korean_names_are_not_claimed():
    for name in ("Taiwan Semiconductor Manufacturing Co Ltd", "Nestle S.A.",
                 "Roche Holding AG", "Apple Inc", "Alibaba Group Holding Ltd",
                 "Tokyo Electron Ltd", "Hong Kong Exchanges & Clearing Ltd"):
        assert not is_korean(name=name), name


def test_us_ticker_is_not_mistaken_for_a_krx_code():
    assert not is_korean(name="Apple Inc", ticker="AAPL")
    assert not is_korean(name="Apple Inc", ticker="12345")     # five digits
    assert not is_korean(name="Apple Inc", ticker="1234567")   # seven digits
