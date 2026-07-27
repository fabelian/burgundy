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
    #
    # The four Canadian managers below are DEACTIVATED. is_active=False takes a
    # manager out of managers.active(), which is what pipeline.run iterates and
    # what the dashboard's picker and every tab resolve against — so one flag
    # both stops all outbound collection for them and removes them from the web
    # app. Nothing already collected is deleted; flipping this back to True
    # restores them with their history intact.
    {
        "slug": "mawer",
        "name": "Mawer Investment Management",
        "legal_name": "MAWER INVESTMENT MANAGEMENT LTD.",
        "cik": "0001538449",
        "crd": "159100",
        "website_aum_url": "https://www.mawer.com/",
        "website_team_url": "https://www.mawer.com/about/team",
        "is_active": False,
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
        "is_active": False,
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
        "is_active": False,
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
        "is_active": False,
        "sort_order": 40,
    },
    # --- US-domiciled advisers -------------------------------------------
    # Firm identity and filing identifiers are separate facts, and each is
    # filled in only when supplied — there is no name-to-CIK resolution here,
    # so Edgar13FCollector.applies() wants the number itself. A blank makes the
    # collector skip, which shows on the panel as "not configured"; a wrong CIK
    # puts another firm's portfolio under this name and looks entirely normal
    # downstream. Only one of those is recoverable, which is why nothing here
    # is inferred from a name.
    #
    # Both are US advisers, unlike the Canadian five, so 13F applies — and a
    # US-registered fund would bring N-PORT, which has no top-N ceiling. See
    # "US-domiciled managers" in docs/korea-holdings.md.
    {
        "slug": "drz",
        "name": "DRZ",
        "legal_name": "DEPRINCE, RACE & ZOLLO, INC.",
        # Supplied directly. Its magnitude corroborates the identity rather
        # than merely fitting it: CIKs are issued in registration order, and
        # ~1,008,894 is a mid-1990s number, matching a firm founded in 1995 —
        # every Canadian manager here registered later and sits above 1.29M.
        "cik": "0001008894",
        "crd": None,
        "website_aum_url": None,
        "website_team_url": None,
        # A deep-value manager running an EM strategy is a far likelier 5%
        # filer in a Korean small cap than the large-cap-oriented Canadians,
        # so the DART safety net is worth arming here even though the rule can
        # never surface a large cap.
        #
        # English spellings only. DART sometimes renders a foreign reporter in
        # Hangul (Burgundy carries both), but the transliteration is not
        # guessable — add it if a known filing is ever missed. "DRZ" itself is
        # too short to match on: three letters appear inside unrelated
        # reporter names.
        "dart_terms": ["DePrince", "Zollo"],
        "sort_order": 50,
    },
    {
        "slug": "kopernik",
        "name": "Kopernik",
        "legal_name": "KOPERNIK GLOBAL INVESTORS, LLC",
        # ~1,599,814 is a 2014-era number, matching a firm founded in 2013 —
        # the highest here, and the only manager registered after Mawer.
        #
        # This is the *adviser's* CIK, which is what 13F is filed under. If the
        # global all-cap strategy is a US-registered fund then its N-PORT is
        # filed by the fund or its trust, under a different CIK entirely — so
        # searching EDGAR under this number will not find it. Search the fund
        # name. See "US-domiciled managers" in docs/korea-holdings.md.
        "cik": "0001599814",
        "crd": None,
        "website_aum_url": "https://www.kopernikglobal.com/",
        # Root only; the team page path has not been seen, and a guessed one
        # would scrape whatever happens to sit there under this firm's name.
        "website_team_url": None,
        "dart_terms": ["Kopernik"],
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
# A URL is recorded only once *seen*, never guessed — the same rule the CIKs
# follow. An invented template would 404 quietly on every run and read as "this
# manager discloses nothing", which is indistinguishable from a real absence.
#
# Registering a fund with **no** URL is a different thing and is fine: it is
# inert (FactsheetCollector._funds() skips it) but visible, appearing on the
# Korea tab's coverage card as 미수집. That turns "we have not got this document
# yet" from an invisible gap into a checklist row. The forbidden move is a
# guessed URL, not a blank one.
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
    # --- awaiting documents ----------------------------------------------
    # Registered by name so the gap is visible rather than invisible; no URL
    # has been seen for any of them, so the collector passes over them and the
    # coverage card shows 미수집.
    #
    # Kopernik: check N-PORT before spending effort on its PDFs. If the
    # all-cap strategy is a US-registered fund, N-PORT gives the whole
    # portfolio monthly and these fact sheets stop being worth parsing at all
    # (docs/korea-holdings.md, "US-domiciled managers").
    {
        "manager_slug": "kopernik",
        "slug": "global-all-cap",
        "name": "Kopernik Global All-Cap",
        "mandate": "global",
        "currency": "USD",
        "cadence": "quarterly",
        "sort_order": 0,
    },
    {
        "manager_slug": "kopernik",
        "slug": "international",
        "name": "Kopernik International",
        "mandate": "international",
        "currency": "USD",
        "cadence": "quarterly",
        "sort_order": 10,
    },
    # DRZ's US Micro/Small/SMID/Large-Cap Value strategies are deliberately
    # absent: a US-only mandate cannot hold a Korean security, so listing one
    # would spend a download to learn nothing. Only the EM strategy qualifies.
    {
        "manager_slug": "drz",
        "slug": "emerging-markets-value",
        "name": "DRZ Emerging Markets Value",
        "mandate": "emerging",
        "currency": "USD",
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
