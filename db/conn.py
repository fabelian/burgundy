"""Database connection helper.

Thin wrapper around psycopg3. Every module opens a short-lived connection via
``connect()`` (context manager) so we never hold pooled state across cron runs.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

import config


@contextlib.contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Yield a psycopg connection with dict rows. Commits on clean exit."""
    conn = psycopg.connect(config.DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
