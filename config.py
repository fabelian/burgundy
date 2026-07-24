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

# SEC IAPD / Form ADV. The adviser's CRD number (Item 5.F RAUM lives here).
# Leave blank to skip Form ADV collection until the CRD is known.
FIRM_CRD = os.environ.get("FIRM_CRD", "")
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
WEEKLY_COLLECTORS = {"form_adv", "website_team", "website_aum"}
