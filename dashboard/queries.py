"""Read-only SQL for each dashboard view."""
from __future__ import annotations

from datetime import date
from typing import Optional

from db.conn import connect
from pipeline import repo


# ---- Overview ------------------------------------------------------------

def aum_series(manager_id: int) -> dict[str, list[dict]]:
    """AUM time series grouped by source (for multi-series line chart)."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT source, as_of_date, aum, currency
              FROM aum_history WHERE manager_id = %s
             ORDER BY source, as_of_date
            """,
            (manager_id,),
        ).fetchall()
    series: dict[str, list[dict]] = {}
    for r in rows:
        series.setdefault(r["source"], []).append({
            "x": r["as_of_date"].isoformat(),
            "y": float(r["aum"]),
            "currency": r["currency"],
        })
    return series


def filing_status(manager_id: int) -> Optional[dict]:
    """Explain the state of 13F reporting for the banner.

    Returns None when there are no notices. Otherwise returns the latest notice
    (quarter, filer that now reports the holdings) plus the last quarter for
    which standalone holdings exist — so the UI can say holdings moved away.
    """
    with connect() as conn:
        notice = conn.execute(
            """
            SELECT as_of_date, filed_at, form, other_managers
              FROM filing_notices WHERE manager_id = %s
             ORDER BY as_of_date DESC, filed_at DESC LIMIT 1
            """,
            (manager_id,),
        ).fetchone()
        if not notice:
            return None
        last_hr = conn.execute(
            "SELECT max(as_of_date) AS d FROM holdings WHERE manager_id = %s",
            (manager_id,),
        ).fetchone()
    return {
        "notice_as_of": notice["as_of_date"],
        "notice_filed_at": notice["filed_at"],
        "other_managers": notice["other_managers"],
        "last_holdings_as_of": last_hr["d"] if last_hr else None,
    }


def aum_table(manager_id: int) -> list[dict]:
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
             WHERE a.manager_id = %s
             ORDER BY a.source, a.as_of_date
            """,
            (manager_id,),
        ).fetchall()
        # Which filing each 13F quarter was summed from — the same selection
        # the series itself uses, so the table explains the number it shows.
        filings = {}
        for r in rows:
            if r["source"] == "13f_total" and r["as_of_date"] not in filings:
                filings[r["as_of_date"]] = repo.best_filing_for_quarter(
                    conn, manager_id, r["as_of_date"])

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


def recent_changes(manager_id: int, limit: int = 5) -> list[dict]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT detected_at, entity_type, change_type, entity_key,
                   before, after, as_of_date
              FROM changes WHERE manager_id = %s
             ORDER BY detected_at DESC, id DESC LIMIT %s
            """,
            (manager_id, limit),
        ).fetchall()


# ---- US Holdings ---------------------------------------------------------

def us_quarters(manager_id: int) -> list[date]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT as_of_date FROM holdings"
            " WHERE manager_id = %s ORDER BY as_of_date DESC",
            (manager_id,),
        ).fetchall()
    return [r["as_of_date"] for r in rows]


def _latest_accession_for_quarter(conn, manager_id: int,
                                  as_of: date) -> Optional[str]:
    """The filing whose holdings represent the quarter — same rule as the
    derived AUM series, so the two tabs never disagree about a quarter."""
    row = repo.best_filing_for_quarter(conn, manager_id, as_of)
    return row["accession_no"] if row else None


# How many positions the composition charts name individually before folding
# the rest into "기타". Six keeps the slices inside the categorical palette's
# gate-safe range, so each one gets its own hue and colour carries identity
# rather than merely rank.
TOP_N = 6


def _composition(conn, manager_id: int, accession: Optional[str],
                 limit: int = TOP_N) -> list[dict]:
    """Largest positions as shares of the filing, with the tail folded in.

    Weights are recomputed from the filing's own values rather than read from
    ``weight``, so a slice always sums against the portfolio actually shown.
    """
    if not accession:
        return []
    rows = conn.execute(
        """
        SELECT cusip, name, ticker, value_kusd
          FROM holdings WHERE manager_id = %s AND accession_no = %s
         ORDER BY value_kusd DESC
        """,
        (manager_id, accession),
    ).fetchall()
    total = sum(int(r["value_kusd"]) for r in rows)
    if total <= 0:
        return []

    out = [{"label": (r["ticker"] or r["name"] or r["cusip"])[:22],
            "name": r["name"],
            "value": int(r["value_kusd"]),
            "pct": round(100 * int(r["value_kusd"]) / total, 2)}
           for r in rows[:limit]]
    tail = sum(int(r["value_kusd"]) for r in rows[limit:])
    if tail > 0:
        out.append({"label": "기타", "name": f"나머지 {len(rows) - limit}종목",
                    "value": tail, "pct": round(100 * tail / total, 2)})
    return out


def us_holdings(manager_id: int, as_of: Optional[date] = None) -> dict:
    """Holdings for a quarter (default latest) with prior-quarter delta."""
    with connect() as conn:
        if as_of is None:
            q = conn.execute(
                "SELECT max(as_of_date) AS d FROM holdings WHERE manager_id = %s",
                (manager_id,),
            ).fetchone()
            as_of = q["d"] if q else None
        if as_of is None:
            return {"as_of": None, "rows": [], "prev": None,
                    "composition": {"current": [], "previous": []}}

        acc = _latest_accession_for_quarter(conn, manager_id, as_of)
        cur = conn.execute(
            """
            SELECT cusip, name, ticker, shares, value_kusd, weight
              FROM holdings WHERE manager_id = %s AND accession_no = %s
             ORDER BY value_kusd DESC
            """,
            (manager_id, acc),
        ).fetchall()

        prev_q = conn.execute(
            "SELECT max(as_of_date) AS d FROM holdings"
            " WHERE manager_id = %s AND as_of_date < %s",
            (manager_id, as_of),
        ).fetchone()
        prev_date = prev_q["d"] if prev_q else None
        prev_map = {}
        prev_acc = None
        if prev_date:
            prev_acc = _latest_accession_for_quarter(conn, manager_id, prev_date)
            for r in conn.execute(
                "SELECT cusip, shares FROM holdings"
                " WHERE manager_id = %s AND accession_no = %s",
                (manager_id, prev_acc),
            ).fetchall():
                prev_map[r["cusip"]] = r["shares"]

        composition = {
            "current": _composition(conn, manager_id, acc),
            "previous": _composition(conn, manager_id, prev_acc),
        }

    out_rows = []
    for r in cur:
        prev_shares = prev_map.get(r["cusip"])
        delta = None if prev_shares is None else int(r["shares"]) - int(prev_shares)
        out_rows.append({**r, "prev_shares": prev_shares, "delta": delta,
                         "is_new": prev_shares is None and prev_date is not None})
    return {"as_of": as_of, "rows": out_rows, "prev": prev_date,
            "composition": composition}


# ---- Korea ---------------------------------------------------------------
#
# The Korea tab is the one view that is deliberately *not* scoped to the
# selected manager. Its question is "which of the five holds Samsung, and how
# much", which is a comparison — showing one manager at a time would mean
# clicking through five tabs to answer it.

def kr_fund_coverage(manager_id: int) -> list[dict]:
    """The selected manager's funds and the freshest document read from each.

    Rendered above the holdings so an empty table can be read correctly: a fund
    with no document collected yet is unknown, not empty, and the two must never
    look the same to someone about to call a client.
    """
    with connect() as conn:
        return conn.execute(
            """
            SELECT m.name AS manager, m.slug AS manager_slug,
                   f.name AS fund, f.mandate, f.cadence,
                   h.latest_as_of, h.positions, h.disclosure_scope
              FROM funds f
              JOIN managers m ON m.id = f.manager_id
              LEFT JOIN LATERAL (
                    SELECT fh.as_of_date AS latest_as_of,
                           count(*) AS positions,
                           max(fh.disclosure_scope) AS disclosure_scope
                      FROM fund_holdings fh
                     WHERE fh.fund_id = f.id
                     GROUP BY fh.as_of_date
                     ORDER BY fh.as_of_date DESC
                     LIMIT 1
              ) h ON TRUE
             WHERE f.is_active AND m.is_active AND f.manager_id = %s
             ORDER BY f.sort_order, f.name
            """,
            (manager_id,),
        ).fetchall()


def kr_evidence(manager_id: int) -> list[dict]:
    """The selected manager's Korean positions, with what each source proves.

    Scoped to one manager like every other tab. It was briefly cross-manager,
    on the reasoning that "which of the five holds Samsung" is a comparison —
    but the manager column is the first thing a narrow screen scrolls out of
    view, which left another firm's Samsung position sitting under the selected
    manager's name. An attribution error is a worse failure than an extra
    click, and the comparison lives in ``kr_peer_holdings`` instead.

    A fact sheet prints only the top 10–25 positions, so it cannot show a
    holding below its smallest printed weight. A voting record has no such
    ceiling but no weight either. Joined, they separate three states that look
    identical in either source alone:

    ``sized``   both agree — held, and measured.
    ``unsized`` a vote but no fact-sheet line — held, and *below the fact
                sheet's floor*. This is the band neither source reaches alone,
                and the reason this query exists.
    ``recent``  a fact-sheet line with no vote — normal for a position opened
                since the voting record's period, which lags about 14 months.

    Keyed on ``(fund_id, security_key)``. The fund is what makes the two sides
    comparable — a voting record is a fund-level obligation, so a fund's sheet
    and that same fund's record describe one portfolio. Keying on the manager
    instead would fold two of its funds holding Samsung into a single row and
    lose one of the positions.

    ``security_key`` is what lets a vote for "Samsung Electronics Co., Ltd."
    meet a holding printed "Samsung Electronics Co Ltd" without either document
    being rewritten.
    """
    with connect() as conn:
        return conn.execute(
            """
            WITH held AS (
                SELECT DISTINCT ON (fh.fund_id, fh.security_key)
                       fh.fund_id, fh.security_key, fh.security_name,
                       fh.weight, fh.as_of_date, fh.disclosure_scope
                  FROM fund_holdings fh
                 WHERE fh.is_korean AND fh.manager_id = %(manager_id)s
                 ORDER BY fh.fund_id, fh.security_key, fh.as_of_date DESC
            ),
            voted AS (
                SELECT DISTINCT ON (pv.fund_id, pv.security_key)
                       pv.fund_id, pv.security_key, pv.issuer_name,
                       pv.meeting_date, pv.period_ended
                  FROM proxy_votes pv
                 WHERE pv.is_korean AND pv.manager_id = %(manager_id)s
                 ORDER BY pv.fund_id, pv.security_key, pv.meeting_date DESC
            ),
            merged AS (
                SELECT COALESCE(h.fund_id, v.fund_id) AS fund_id,
                       COALESCE(h.security_name, v.issuer_name) AS security_name,
                       h.weight, h.as_of_date, h.disclosure_scope,
                       v.meeting_date, v.period_ended,
                       CASE WHEN h.fund_id IS NOT NULL
                             AND v.fund_id IS NOT NULL THEN 'sized'
                            WHEN h.fund_id IS NULL      THEN 'unsized'
                            ELSE 'recent' END AS evidence
                  FROM held h
                  FULL OUTER JOIN voted v
                       ON v.fund_id = h.fund_id
                      AND v.security_key = h.security_key
            )
            SELECT f.name AS fund, g.security_name, g.weight, g.as_of_date,
                   g.disclosure_scope, g.meeting_date, g.period_ended,
                   g.evidence
              FROM merged g
              JOIN funds f ON f.id = g.fund_id
             ORDER BY g.weight DESC NULLS LAST, f.name, g.security_name
            """,
            {"manager_id": manager_id},
        ).fetchall()


def kr_peer_holdings(manager_id: int) -> list[dict]:
    """The *other* managers' Korean positions, for comparison.

    Deliberately excludes the selected manager rather than highlighting it.
    Mixing the two in one table is what made the manager column load-bearing,
    and a load-bearing column that scrolls off a phone misattributes holdings.
    Here every row belongs to someone else by construction, so there is nothing
    to misread even with the table scrolled.
    """
    with connect() as conn:
        return conn.execute(
            """
            SELECT DISTINCT ON (fh.manager_id, fh.security_key)
                   m.name AS manager, m.slug AS manager_slug,
                   f.name AS fund, fh.security_name, fh.weight, fh.as_of_date
              FROM fund_holdings fh
              JOIN funds f    ON f.id = fh.fund_id
              JOIN managers m ON m.id = fh.manager_id
             WHERE fh.is_korean AND fh.manager_id <> %s AND m.is_active
             ORDER BY fh.manager_id, fh.security_key, fh.as_of_date DESC
            """,
            (manager_id,),
        ).fetchall()


def kr_weight_series(manager_id: int) -> dict[str, list[dict]]:
    """Korean weight over time for one manager, one line per fund+security."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.name AS manager, f.name AS fund, fh.security_name,
                   fh.as_of_date, fh.weight
              FROM fund_holdings fh
              JOIN funds f    ON f.id = fh.fund_id
              JOIN managers m ON m.id = fh.manager_id
             WHERE fh.is_korean AND fh.weight IS NOT NULL
               AND fh.manager_id = %s
             ORDER BY f.name, fh.security_name, fh.as_of_date
            """,
            (manager_id,),
        ).fetchall()
    series: dict[str, list[dict]] = {}
    for r in rows:
        label = f"{r['fund']} · {r['security_name']}"
        series.setdefault(label, []).append({
            "x": r["as_of_date"].isoformat(),
            "y": float(r["weight"]),
        })
    return series


def kr_series(manager_id: int) -> dict[str, list[dict]]:
    """Ownership-pct trend per corp for the chart."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT corp_name, as_of_date, ownership_pct
              FROM kr_holdings
             WHERE manager_id = %s AND ownership_pct IS NOT NULL
             ORDER BY corp_name, as_of_date
            """,
            (manager_id,),
        ).fetchall()
    series: dict[str, list[dict]] = {}
    for r in rows:
        series.setdefault(r["corp_name"], []).append({
            "x": r["as_of_date"].isoformat(),
            "y": float(r["ownership_pct"]),
        })
    return series


def kr_history(manager_id: int) -> list[dict]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT as_of_date, filed_at, rcept_no, corp_name, ticker,
                   shares, ownership_pct, report_type
              FROM kr_holdings WHERE manager_id = %s
             ORDER BY filed_at DESC, corp_name
            """,
            (manager_id,),
        ).fetchall()


# ---- Changes -------------------------------------------------------------

def changes(manager_id: int, entity_type: Optional[str] = None,
            limit: int = 200) -> list[dict]:
    q = ("SELECT detected_at, entity_type, change_type, entity_key, "
         "before, after, as_of_date FROM changes WHERE manager_id = %s")
    params: tuple = (manager_id,)
    if entity_type and entity_type != "all":
        q += " AND entity_type = %s"
        params = params + (entity_type,)
    q += " ORDER BY detected_at DESC, id DESC LIMIT %s"
    params = params + (limit,)
    with connect() as conn:
        return conn.execute(q, params).fetchall()


def collector_status(manager_id: int, limit: int = 20) -> list[dict]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT collector, started_at, finished_at, status,
                   new_raw, new_rows, error_msg
              FROM collector_runs WHERE manager_id = %s
             ORDER BY started_at DESC LIMIT %s
            """,
            (manager_id, limit),
        ).fetchall()


# ---- Managers ------------------------------------------------------------

def manager_list() -> list[dict]:
    """Tracked managers plus a coverage hint for the picker."""
    with connect() as conn:
        return conn.execute(
            """
            SELECT m.id, m.slug, m.name, m.cik,
                   (SELECT count(DISTINCT as_of_date) FROM holdings h
                     WHERE h.manager_id = m.id) AS quarters
              FROM managers m
             WHERE m.is_active
             ORDER BY m.sort_order, m.name
            """
        ).fetchall()


def manager_by_slug(slug: Optional[str]) -> Optional[dict]:
    """Resolve the selected manager, falling back to the first tracked one."""
    with connect() as conn:
        if slug:
            row = conn.execute(
                "SELECT * FROM managers WHERE slug = %s AND is_active", (slug,)
            ).fetchone()
            if row:
                return row
        return conn.execute(
            "SELECT * FROM managers WHERE is_active"
            " ORDER BY sort_order, name LIMIT 1"
        ).fetchone()
