"""Optional Telegram notifications for new change events.

If TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are unset, everything silently no-ops.
"""
from __future__ import annotations

import httpx

import config


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def send(text: str) -> None:
    if not enabled():
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        httpx.post(url, json={"chat_id": config.TELEGRAM_CHAT_ID,
                              "text": text, "parse_mode": "HTML"}, timeout=15)
    except Exception as exc:  # notifications must never break the run
        print(f"[notify] telegram send failed: {exc}")


def format_change(row: dict) -> str:
    return (f"<b>{row['change_type']}</b> [{row['entity_type']}] "
            f"{row['entity_key']}"
            + (f" @ {row['as_of_date']}" if row.get("as_of_date") else ""))
