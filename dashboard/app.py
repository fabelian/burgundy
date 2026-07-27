"""FastAPI dashboard.

Single page with HTMX-loaded tabs: Overview / US Holdings / Korea / Changes.
HTTP Basic auth is applied when DASHBOARD_PASSWORD is set.
"""
from __future__ import annotations

import json
import secrets
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dateutil import parser as dateparse
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

import config
from dashboard import queries

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Burgundy Tracker")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
security = HTTPBasic(auto_error=False)


def _json_default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


def _tojson_safe(value) -> Markup:
    """JSON for embedding inside a <script> block.

    Must be marked safe: Jinja2 autoescapes plain strings, and HTML entities are
    not decoded inside <script>, so an escaped quote reaches the JS parser
    verbatim and kills the whole block. Characters that could break out of the
    tag are emitted as \\u escapes instead, which stay valid JSON.
    """
    payload = json.dumps(value, default=_json_default)
    for char, escape in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                         ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        payload = payload.replace(char, escape)
    return Markup(payload)


templates.env.filters["tojson_safe"] = _tojson_safe


def require_auth(credentials: Optional[HTTPBasicCredentials] = Depends(security)):
    if not config.DASHBOARD_PASSWORD:
        return True  # auth disabled
    if credentials is None or not secrets.compare_digest(
        credentials.password, config.DASHBOARD_PASSWORD
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, manager: Optional[str] = Query(None),
          _=Depends(require_auth)):
    selected = queries.manager_by_slug(manager)
    return templates.TemplateResponse(request, "index.html", {
        "manager": selected["name"] if selected else config.MANAGER_NAME,
        "managers": queries.manager_list(),
        "selected": selected["slug"] if selected else None,
    })


def _resolve(slug: Optional[str]):
    """Every tab renders for exactly one manager; an unknown slug falls back
    to the first tracked one rather than leaking another manager's data."""
    selected = queries.manager_by_slug(slug)
    if selected is None:
        raise HTTPException(status_code=404, detail="no managers tracked")
    return selected


# ---- HTMX partials -------------------------------------------------------

@app.get("/tab/overview", response_class=HTMLResponse)
def tab_overview(request: Request, manager: Optional[str] = Query(None),
                 _=Depends(require_auth)):
    m = _resolve(manager)
    return templates.TemplateResponse(request, "overview.html", {
        "aum_series": queries.aum_series(m["id"]),
        "recent": queries.recent_changes(m["id"], 5),
        "collectors": queries.collector_status(m["id"], 8),
        "filing_status": queries.filing_status(m["id"]),
        "selected": m["slug"],
    })


@app.get("/tab/aum", response_class=HTMLResponse)
def tab_aum(request: Request, manager: Optional[str] = Query(None),
            _=Depends(require_auth)):
    m = _resolve(manager)
    return templates.TemplateResponse(request, "aum.html", {
        "aum_series": queries.aum_series(m["id"]),
        "table": queries.aum_table(m["id"]),
        "filing_status": queries.filing_status(m["id"]),
        "selected": m["slug"],
    })


@app.get("/tab/us", response_class=HTMLResponse)
def tab_us(request: Request, quarter: Optional[str] = Query(None),
           manager: Optional[str] = Query(None), _=Depends(require_auth)):
    m = _resolve(manager)
    as_of = dateparse.parse(quarter).date() if quarter else None
    return templates.TemplateResponse(request, "us_holdings.html", {
        "data": queries.us_holdings(m["id"], as_of),
        "quarters": queries.us_quarters(m["id"]),
        "filing_status": queries.filing_status(m["id"]),
        "selected": m["slug"],
    })


@app.get("/tab/korea", response_class=HTMLResponse)
def tab_korea(request: Request, manager: Optional[str] = Query(None),
              _=Depends(require_auth)):
    m = _resolve(manager)
    # Scoped to the selected manager, like every other tab.
    return templates.TemplateResponse(request, "korea.html", {
        "manager_name": m["name"],
        "coverage": queries.kr_fund_coverage(m["id"]),
        # The registry is populated by pipeline.run, not by the dashboard, so
        # between a deploy and the next collector run the table is empty while
        # config is not. Passing the configured count lets the tab tell those
        # two apart instead of reporting "no funds tracked" when one is.
        #
        # Counted for *this* manager: now that coverage is scoped, a global
        # count would tell a manager with nothing configured that a fund of
        # someone else's is merely waiting to sync.
        "configured_funds": sum(1 for f in config.FUNDS
                                if f["manager_slug"] == m["slug"]),
        "evidence": queries.kr_evidence(m["id"]),
        "weight_series": queries.kr_weight_series(m["id"]),
        "kr_series": queries.kr_series(m["id"]),
        "history": queries.kr_history(m["id"]),
        "selected": m["slug"],
    })


@app.get("/tab/changes", response_class=HTMLResponse)
def tab_changes(request: Request, entity_type: str = Query("all"),
                manager: Optional[str] = Query(None), _=Depends(require_auth)):
    m = _resolve(manager)
    return templates.TemplateResponse(request, "changes.html", {
        "changes": queries.changes(m["id"], entity_type),
        "entity_type": entity_type,
        "selected": m["slug"],
    })
