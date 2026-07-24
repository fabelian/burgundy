"""Shared HTTP helpers with SEC/DART etiquette (User-Agent + rate limiting)."""
from __future__ import annotations

import time

import httpx

import config

_last_sec_request = [0.0]


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
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.text
