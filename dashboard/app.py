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
def index(request: Request, _=Depends(require_auth)):
    return templates.TemplateResponse(
        request, "index.html", {"manager": config.MANAGER_NAME}
    )


# ---- HTMX partials -------------------------------------------------------

@app.get("/tab/overview", response_class=HTMLResponse)
def tab_overview(request: Request, _=Depends(require_auth)):
    return templates.TemplateResponse(request, "overview.html", {
        "aum_series": queries.aum_series(),
        "recent": queries.recent_changes(5),
        "collectors": queries.collector_status(8),
        "filing_status": queries.filing_status(),
    })


@app.get("/tab/aum", response_class=HTMLResponse)
def tab_aum(request: Request, _=Depends(require_auth)):
    return templates.TemplateResponse(request, "aum.html", {
        "aum_series": queries.aum_series(),
        "table": queries.aum_table(),
        "filing_status": queries.filing_status(),
    })


@app.get("/tab/us", response_class=HTMLResponse)
def tab_us(request: Request, quarter: Optional[str] = Query(None),
           _=Depends(require_auth)):
    as_of = dateparse.parse(quarter).date() if quarter else None
    data = queries.us_holdings(as_of)
    return templates.TemplateResponse(request, "us_holdings.html", {
        "data": data,
        "quarters": queries.us_quarters(),
        "filing_status": queries.filing_status(),
    })


@app.get("/tab/korea", response_class=HTMLResponse)
def tab_korea(request: Request, _=Depends(require_auth)):
    return templates.TemplateResponse(request, "korea.html", {
        "kr_series": queries.kr_series(),
        "history": queries.kr_history(),
    })


@app.get("/tab/changes", response_class=HTMLResponse)
def tab_changes(request: Request, entity_type: str = Query("all"),
                _=Depends(require_auth)):
    return templates.TemplateResponse(request, "changes.html", {
        "changes": queries.changes(entity_type),
        "entity_type": entity_type,
    })
