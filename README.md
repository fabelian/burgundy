# Burgundy Asset Management Tracker

Periodically collects and **permanently preserves** the public footprint of
[Burgundy Asset Management](https://www.burgundyasset.com/) (Toronto; SEC CIK
`0001315868`):

- **US holdings** — SEC EDGAR 13F-HR filings (incl. amendments)
- **Korean stakes** — DART 대량보유상황보고 (5%+ disclosures)
- **AUM** — SEC Form ADV RAUM, 13F totals, website figure
- **People** — Form ADV Schedule A + company team page

Everything is stored **append-only**. Snapshots are never updated or deleted;
corrections/amendments arrive as new rows. Every change is diffed into a
`changes` event stream.

## Design: three storage layers

```
raw_documents   immutable originals (XML/JSON/HTML) — never re-fetched to rebuild
      │
snapshot tables holdings / kr_holdings / aum_history / personnel  (append-only)
      │
changes         diff events (NEW_POSITION, EXITED, STAKE_CHANGED, TITLE_CHANGED, …)
```

Bitemporal dates are always separated: `as_of_date` (disclosure basis),
`filed_at` (filing date), `fetched_at` (collection time).

Idempotency keys — EDGAR `accession_no`, DART `rcept_no`, scrapes `content_hash`
— make every collector safe to re-run. `personnel` is the one SCD Type 2 table
(`valid_from` / `valid_to`).

## Layout

```
config.py            # all source constants (CIK, DART terms, URLs) — swap to track another manager
db/                  # migrate.py runner + migrations/001_init.sql
collectors/          # BaseCollector + edgar_13f / dart_5pct / form_adv / website
parsers/             # pure functions: parse_13f / parse_dart / parse_website
pipeline/            # run.py (cron) · diff.py · backfill.py · reparse.py · repo.py · notify.py
dashboard/           # FastAPI + Jinja2 + HTMX + Chart.js
tests/               # fixtures + parser/diff tests
```

## Local development

```bash
pip install -e .            # or: pip install -e '.[dev]' for pytest
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/burgundy"
export SEC_USER_AGENT="burgundy-tracker your-email@example.com"

python -m db.migrate                       # create/upgrade schema
python -m pipeline.backfill --since 2015   # load historical 13F quarters
python -m pipeline.run                     # one full collection cycle
uvicorn dashboard.app:app --reload         # dashboard at http://localhost:8000

pytest                                     # tests (DB-backed ones skip if no DB)
```

### Useful commands

| Command | Purpose |
|---|---|
| `python -m db.migrate` | Apply pending SQL migrations (idempotent) |
| `python -m pipeline.run` | Cron entrypoint — runs all collectors |
| `python -m pipeline.backfill --since 2015 [--limit N]` | Backfill historical 13F filings |
| `python -m pipeline.reparse [--source edgar_13f]` | Rebuild snapshots from stored raw docs |

## Environment variables

| Var | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Postgres DSN (auto-injected on Railway) |
| `SEC_USER_AGENT` | yes | `"burgundy-tracker you@example.com"` — SEC requires a real contact |
| `DART_API_KEY` | for Korea | Issue at https://opendart.fss.or.kr |
| `FIRM_CRD` | for Form ADV | Adviser CRD number; Form ADV is skipped when unset |
| `DASHBOARD_PASSWORD` | optional | Enables HTTP Basic auth on the dashboard |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | optional | Push change alerts; silently skipped when unset |

## Deployment (Railway)

One repository, **two services** sharing the Postgres plugin and the env vars
above. `railway.json` configures the always-on dashboard by default; add the
collector as a second service in the Railway dashboard.

| Service | Start command | Setting |
|---|---|---|
| `dashboard` | `python -m db.migrate && uvicorn dashboard.app:app --host 0.0.0.0 --port $PORT` | always on (this is `railway.json`) |
| `collector` | `python -m db.migrate && python -m pipeline.run` | Cron `0 22 * * *` (UTC 22:00 = KST 07:00, daily) |

Steps:
1. Create a Railway project from this repo and add the **PostgreSQL** plugin.
2. Service **dashboard** deploys automatically from `railway.json`.
3. Add a second service **collector** from the same repo, set its start command
   and Cron schedule as above, and share the same variables.
4. Set the env vars in the shared project variables.

The collector branches internally by cadence: EDGAR and DART run every
invocation; Form ADV and the website scrapes are skipped when their last
successful run (per `collector_runs`) is within 7 days. Every run — success,
skip, or error — is recorded in `collector_runs` for operational visibility.

## Dashboard views

- **Overview** — AUM time series (per source) + recent changes + collector runs
- **US Holdings** — latest quarter (by weight) with prior-quarter share deltas and a quarter dropdown for historical snapshots
- **Korea** — ownership-% trend chart + disclosure history, with a fixed banner that only 5%+ disclosures are captured
- **Changes** — full diff timeline with an entity-type filter

## Data limitations

- Korean holdings reflect **only 5%+ 대량보유 disclosures**; smaller stakes are not publicly disclosed.
- 13F covers **US-listed** long positions only (no shorts, cash, or non-US securities).
