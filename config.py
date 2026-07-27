"""Central configuration.

All source-specific constants live here so a new manager can be tracked by
swapping the values below (CIK, DART search terms, website URLs) without
touching collector/parser code.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Target manager
# ---------------------------------------------------------------------------
MANAGER_NAME = "Burgundy Asset Management"

# SEC EDGAR
CIK = "0001315868"                     # zero-padded 10-digit CIK
CIK_INT = int(CIK)                     # for endpoints that want no padding

# ---------------------------------------------------------------------------
# Tracked managers
# ---------------------------------------------------------------------------
# Rows are upserted into the ``managers`` table on every migrate/run, keyed by
# slug, so adding a peer here is the whole job.
#
# ``cik`` is left None for anyone whose CIK has not been confirmed: the EDGAR
# collector resolves it by name on first run and writes it back. A guessed CIK
# would silently track the wrong company, which is worse than not tracking one.
# ``crd`` and the website URLs are optional — the Form ADV and website
# collectors skip a manager that has none rather than scraping a wrong site.
MANAGERS = [
    {
        "slug": "burgundy",
        "name": "Burgundy Asset Management",
        "legal_name": "BURGUNDY ASSET MANAGEMENT LTD.",
        "cik": "0001315868",
        "crd": os.environ.get("FIRM_CRD", "114317"),
        "website_aum_url": "https://www.burgundyasset.com/",
        "website_team_url": "https://www.burgundyasset.com/about-us/our-team/",
        "dart_terms": ["버건디", "Burgundy"],
        "sort_order": 0,
    },
    # CIKs below are each confirmed from that filer's own sec.gov/Archives
    # 13F-HR documents, not inferred from a name search.
    {
        "slug": "mawer",
        "name": "Mawer Investment Management",
        "legal_name": "MAWER INVESTMENT MANAGEMENT LTD.",
        "cik": "0001538449",
        "crd": "159100",
        "website_aum_url": "https://www.mawer.com/",
        "website_team_url": "https://www.mawer.com/about/team",
        "sort_order": 10,
    },
    {
        "slug": "edgepoint",
        "name": "EdgePoint Investment Group",
        "legal_name": "EDGEPOINT INVESTMENT GROUP INC.",
        "cik": "0001481669",
        "crd": "312152",
        "website_aum_url": "https://www.edgepointwealth.com/",
        "website_team_url": "https://www.edgepointwealth.com/your-team/",
        "sort_order": 20,
    },
    {
        "slug": "beutel-goodman",
        "name": "Beutel Goodman & Company",
        "legal_name": "BEUTEL, GOODMAN & CO LTD.",
        "cik": "0001361974",
        "crd": "135829",
        "website_aum_url": "https://www.beutelgoodman.com/",
        "website_team_url": "https://www.beutelgoodman.com/team/",
        "sort_order": 30,
    },
    {
        "slug": "letko-brosseau",
        "name": "Letko Brosseau & Associates",
        "legal_name": "LETKO, BROSSEAU & ASSOCIATES INC",
        "cik": "0001297496",
        "crd": "133221",
        "website_aum_url": "https://www.lba.ca/",
        "website_team_url": "https://www.lba.ca/teams/",
        "sort_order": 40,
    },
    # --- US-domiciled advisers -------------------------------------------
    # Added later and deliberately incomplete. Every identifier above was read
    # off that filer's own EDGAR documents; none of these could be, so they are
    # left NULL rather than guessed. The cost of a blank is that EDGAR, Form ADV
    # and the website scrapes skip the manager — visible on the collector panel.
    # The cost of a wrong CIK is another firm's portfolio under this name, with
    # nothing downstream looking wrong. Fill them in from the filer's own
    # documents, not from a name search.
    #
    # Unlike the five Canadian managers, both are US advisers, so 13F applies to
    # them — and a US-registered fund would bring N-PORT, which has no top-N
    # ceiling. See "US-domiciled managers" in docs/korea-holdings.md.
    {
        "slug": "drz",
        "name": "DRZ",
        # Very likely DePrince, Race & Zollo (Winter Park, FL — long-only US
        # value plus an EM Value strategy). Not recorded as legal_name until
        # confirmed: a name is what dart_terms and the ADV lookup key off.
        "legal_name": None,
        "cik": None,
        "crd": None,
        "website_aum_url": None,
        "website_team_url": None,
        "sort_order": 50,
    },
    {
        "slug": "kopernik",
        "name": "Kopernik",
        # Very likely Kopernik Global Investors, LLC (Tampa, FL). Its global
        # all-cap strategy appears to be a US-registered fund, which would make
        # N-PORT available — month-end, position-level, whole portfolio.
        "legal_name": None,
        "cik": None,
        "crd": None,
        "website_aum_url": None,
        "website_team_url": None,
        "sort_order": 60,
    },
]

# ---------------------------------------------------------------------------
# Tracked funds (fact-sheet holdings)
# ---------------------------------------------------------------------------
# Upserted into the ``funds`` table on every migrate/run, keyed by
# (manager slug, fund slug).
#
# Only International / Global / Emerging Markets mandates belong here: a
# Canadian or US-only fund cannot hold a Korean security, so listing one would
# spend a download to learn nothing (docs/korea-holdings.md).
#
# ``doc_url_template`` is expanded per period by the fact-sheet collector.
# Placeholders: {q} quarter 1-4, {yy} 2-digit year, {yyyy} 4-digit year,
# {mm} 2-digit month.
#
# The list is short on purpose. A fund is added once its document URL has been
# *seen*, not guessed — the same rule the CIKs above follow. The remaining four
# managers' International/Global/EM funds still need enumerating against their
# live sites; a template invented here would 404 quietly on every run and read
# as "this manager discloses nothing".
FUNDS = [
    {
        "manager_slug": "mawer",
        "slug": "international-equity",
        "name": "Mawer International Equity Fund",
        "mandate": "international",
        "series": "Series F",
        "currency": "CAD",
        # Two shapes, both kept: series differ in fees, not in holdings, so
        # either document answers the Korean question.
        #
        # The per-quarter path is where Samsung Electronics at 1.7% was read
        # (docs/korea-holdings.md). Mawer has since moved its assets behind a
        # CDN, so this may no longer resolve — it is left in because it is the
        # only route to *past* quarters, and a 404 costs one request.
        "doc_url_template": (
            "https://www.mawer.com/mawer-com-cms/assets/funds/"
            "{q}q{yy}-mawer-international-equity-fund-series-a.pdf"
        ),
        # The current CDN asset. Carries no period: the contents are replaced
        # each quarter, so this is always the latest sheet and never a
        # historical one.
        "doc_url": (
            "https://az-prd-mawer-com-cms-bda9ehd8a2fqgdgn.a02.azurefd.net/"
            "mawer-com-cms/assets/"
            "Mawer_International_Equity_Fund_Series_F_24a4cbc644.pdf"
        ),
        "cadence": "quarterly",
        "sort_order": 0,
    },
]

# SEC IAPD / Form ADV. The adviser's CRD number (Item 5.F RAUM lives here).
# Burgundy's CRD is 114317 (from its 13F cover page). Form ADV / RAUM is filed
# independently of 13F, so it remains a live AUM source even now that Burgundy's
# 13F holdings are reported by its acquirer. Override via env if needed.
FIRM_CRD = os.environ.get("FIRM_CRD", "114317")
IAPD_FIRM_URL = "https://api.adviserinfo.sec.gov/search/firm/{crd}"

# DART reporter-name search terms (대량보유상황보고 보고자명 매칭)
DART_SEARCH_TERMS = ["버건디", "Burgundy"]

# Company website
WEBSITE_TEAM_URL = "https://www.burgundyasset.com/about-us/our-team/"
WEBSITE_AUM_URL = "https://www.burgundyasset.com/"

# ---------------------------------------------------------------------------
# EDGAR access rules
# ---------------------------------------------------------------------------
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "burgundy-tracker contact@example.com")
SEC_SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{CIK}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
SEC_RATE_LIMIT_SLEEP = 0.2             # seconds between requests (<10 req/s)

# ---------------------------------------------------------------------------
# DART access rules
# ---------------------------------------------------------------------------
DART_API_KEY = os.environ.get("DART_API_KEY", "")
# Client-side gap between JSON API calls (DART). A multi-year sweep is
# thousands of requests; unthrottled it reaches the daily quota at network speed.
JSON_RATE_LIMIT_SLEEP = float(os.environ.get("JSON_RATE_LIMIT_SLEEP", "0.15"))
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_MAJORSTOCK_URL = "https://opendart.fss.or.kr/api/majorstock.json"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/burgundy")

# ---------------------------------------------------------------------------
# Notifications (optional)
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")

# ---------------------------------------------------------------------------
# Collector cadence: sources that only need weekly refresh
# ---------------------------------------------------------------------------
WEEKLY_REFRESH_DAYS = 7
WEEKLY_COLLECTORS = {"form_adv", "website_team", "website_aum", "factsheet"}
