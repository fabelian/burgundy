import os

import pytest

# Ensure a DATABASE_URL default for local test runs.
os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/burgundy"
)


@pytest.fixture
def db():
    """Yield a connection to a migrated DB, cleaning mutated tables first.

    Skips the test if no database is reachable.
    """
    try:
        from db.conn import connect
        with connect() as conn:
            conn.execute("TRUNCATE holdings, kr_holdings, aum_history, personnel, "
                         "changes, raw_documents RESTART IDENTITY CASCADE")
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"database not available: {exc}")

    from db.conn import connect
    with connect() as conn:
        yield conn
