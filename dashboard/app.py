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
from fastapi.templating import Jinja2Templates

import config
from dashboard import queries

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Burgundy Tracker")
security = HTTPBasic(auto_error=False)


def _json_default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


templates.env.filters["tojson_safe"] = lambda v: json.dumps(v, default=_json_default)


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
    })


@app.get("/tab/us", response_class=HTMLResponse)
def tab_us(request: Request, quarter: Optional[str] = Query(None),
           _=Depends(require_auth)):
    as_of = dateparse.parse(quarter).date() if quarter else None
    data = queries.us_holdings(as_of)
    return templates.TemplateResponse(request, "us_holdings.html", {
        "data": data,
        "quarters": queries.us_quarters(),
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
