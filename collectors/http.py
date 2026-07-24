"""Shared HTTP helpers with SEC/DART etiquette (User-Agent + rate limiting)."""
from __future__ import annotations

import time

import httpx

import config

_last_sec_request = [0.0]

# Many corporate sites (incl. burgundyasset.com) 403 non-browser clients, so
# website scrapes send a realistic browser User-Agent.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def sec_get(url: str, *, timeout: float = 30.0) -> httpx.Response:
    """GET against SEC hosts with the required User-Agent and rate limiting."""
    # simple client-side throttle: >= SEC_RATE_LIMIT_SLEEP between requests
    elapsed = time.monotonic() - _last_sec_request[0]
    if elapsed < config.SEC_RATE_LIMIT_SLEEP:
        time.sleep(config.SEC_RATE_LIMIT_SLEEP - elapsed)
    headers = {
        "User-Agent": config.SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }
    resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    _last_sec_request[0] = time.monotonic()
    resp.raise_for_status()
    return resp


def get_json(url: str, *, params: dict | None = None, timeout: float = 30.0) -> dict:
    resp = httpx.get(url, params=params, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def get_text(url: str, *, timeout: float = 30.0) -> str:
    resp = httpx.get(url, headers=BROWSER_HEADERS, timeout=timeout,
                     follow_redirects=True)
    resp.raise_for_status()
    return resp.text
