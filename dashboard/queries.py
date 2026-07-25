"""Read-only SQL for each dashboard view."""
from __future__ import annotations

from datetime import date
from typing import Optional

from db.conn import connect
from pipeline import repo


# ---- Overview ------------------------------------------------------------

def aum_series() -> dict[str, list[dict]]:
    """AUM time series grouped by source (for multi-series line chart)."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT source, as_of_date, aum, currency
              FROM aum_history ORDER BY source, as_of_date
            """
        ).fetchall()
    series: dict[str, list[dict]] = {}
    for r in rows:
        series.setdefault(r["source"], []).append({
            "x": r["as_of_date"].isoformat(),
            "y": float(r["aum"]),
            "currency": r["currency"],
        })
    return series


def filing_status() -> Optional[dict]:
    """Explain the state of 13F reporting for the banner.

    Returns None when there are no notices. Otherwise returns the latest notice
    (quarter, filer that now reports the holdings) plus the last quarter for
    which standalone holdings exist — so the UI can say holdings moved away.
    """
    with connect() as conn:
        notice = conn.execute(
            """
            SELECT as_of_date, filed_at, form, other_managers
              FROM filing_notices ORDER BY as_of_date DESC, filed_at DESC LIMIT 1
            """
        ).fetchone()
        if not notice:
            return None
        last_hr = conn.execute("SELECT max(as_of_date) AS d FROM holdings").fetchone()
    return {
        "notice_as_of": notice["as_of_date"],
        "notice_filed_at": notice["filed_at"],
        "other_managers": notice["other_managers"],
        "last_holdings_as_of": last_hr["d"] if last_hr else None,
    }


def aum_table() -> list[dict]:
    """Every AUM observation with its provenance, newest first.

    ``ratio`` compares each value with the previous one for the *same* source,
    so a mis-scaled or corrupt filing stands out as an order-of-magnitude jump
    rather than hiding inside a chart whose axis it has already flattened.
    """
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT a.as_of_date, a.source, a.aum, a.currency, a.fetched_at,
                   r.external_id AS accession_no, r.url AS source_url
              FROM aum_history a
              LEFT JOIN raw_documents r ON r.id = a.raw_id
             ORDER BY a.source, a.as_of_date
            """
        ).fetchall()
        # Which filing each 13F quarter was summed from — the same selection
        # the series itself uses, so the table explains the number it shows.
        filings = {}
        for r in rows:
            if r["source"] == "13f_total" and r["as_of_date"] not in filings:
                filings[r["as_of_date"]] = repo.best_filing_for_quarter(
                    conn, r["as_of_date"])

    out: list[dict] = []
    prev: dict[str, float] = {}
    for r in rows:
        current = float(r["aum"])
        previous = prev.get(r["source"])
        ratio = current / previous if previous else None
        best = filings.get(r["as_of_date"]) if r["source"] == "13f_total" else None
        out.append({
            **r,
            "positions": best["positions"] if best else None,
            "is_amendment": best["is_amendment"] if best else None,
            "filings": best["filings"] if best else None,
            "aum": current,
            "prev_aum": previous,
            "ratio": ratio,
            "suspect": ratio is not None and (ratio >= 10 or ratio <= 0.1),
        })
        prev[r["source"]] = current

    out.sort(key=lambda x: (x["as_of_date"], x["source"]), reverse=True)
    return out


def recent_changes(limit: int = 5) -> list[dict]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT detected_at, entity_type, change_type, entity_key,
                   before, after, as_of_date
              FROM changes ORDER BY detected_at DESC, id DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()


# ---- US Holdings ---------------------------------------------------------

def us_quarters() -> list[date]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT as_of_date FROM holdings ORDER BY as_of_date DESC"
        ).fetchall()
    return [r["as_of_date"] for r in rows]


def _latest_accession_for_quarter(conn, as_of: date) -> Optional[str]:
    """The filing whose holdings represent the quarter — same rule as the
    derived AUM series, so the two tabs never disagree about a quarter."""
    row = repo.best_filing_for_quarter(conn, as_of)
    return row["accession_no"] if row else None


def us_holdings(as_of: Optional[date] = None) -> dict:
    """Holdings for a quarter (default latest) with prior-quarter delta."""
    with connect() as conn:
        if as_of is None:
            q = conn.execute(
                "SELECT max(as_of_date) AS d FROM holdings"
            ).fetchone()
            as_of = q["d"] if q else None
        if as_of is None:
            return {"as_of": None, "rows": [], "prev": None}

        acc = _latest_accession_for_quarter(conn, as_of)
        cur = conn.execute(
            """
            SELECT cusip, name, ticker, shares, value_kusd, weight
              FROM holdings WHERE accession_no = %s
             ORDER BY value_kusd DESC
            """,
            (acc,),
        ).fetchall()

        prev_q = conn.execute(
            "SELECT max(as_of_date) AS d FROM holdings WHERE as_of_date < %s",
            (as_of,),
        ).fetchone()
        prev_date = prev_q["d"] if prev_q else None
        prev_map = {}
        if prev_date:
            prev_acc = _latest_accession_for_quarter(conn, prev_date)
            for r in conn.execute(
                "SELECT cusip, shares FROM holdings WHERE accession_no = %s",
                (prev_acc,),
            ).fetchall():
                prev_map[r["cusip"]] = r["shares"]

    out_rows = []
    for r in cur:
        prev_shares = prev_map.get(r["cusip"])
        delta = None if prev_shares is None else int(r["shares"]) - int(prev_shares)
        out_rows.append({**r, "prev_shares": prev_shares, "delta": delta,
                         "is_new": prev_shares is None and prev_date is not None})
    return {"as_of": as_of, "rows": out_rows, "prev": prev_date}


# ---- Korea ---------------------------------------------------------------

def kr_series() -> dict[str, list[dict]]:
    """Ownership-pct trend per corp for the chart."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT corp_name, as_of_date, ownership_pct
              FROM kr_holdings
             WHERE ownership_pct IS NOT NULL
             ORDER BY corp_name, as_of_date
            """
        ).fetchall()
    series: dict[str, list[dict]] = {}
    for r in rows:
        series.setdefault(r["corp_name"], []).append({
            "x": r["as_of_date"].isoformat(),
            "y": float(r["ownership_pct"]),
        })
    return series


def kr_history() -> list[dict]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT as_of_date, filed_at, rcept_no, corp_name, ticker,
                   shares, ownership_pct, report_type
              FROM kr_holdings ORDER BY filed_at DESC, corp_name
            """
        ).fetchall()


# ---- Changes -------------------------------------------------------------

def changes(entity_type: Optional[str] = None, limit: int = 200) -> list[dict]:
    q = ("SELECT detected_at, entity_type, change_type, entity_key, "
         "before, after, as_of_date FROM changes")
    params: tuple = ()
    if entity_type and entity_type != "all":
        q += " WHERE entity_type = %s"
        params = (entity_type,)
    q += " ORDER BY detected_at DESC, id DESC LIMIT %s"
    params = params + (limit,)
    with connect() as conn:
        return conn.execute(q, params).fetchall()


def collector_status(limit: int = 20) -> list[dict]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT collector, started_at, finished_at, status,
                   new_raw, new_rows, error_msg
              FROM collector_runs ORDER BY started_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
