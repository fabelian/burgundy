# North American Asset Manager Tracker

Periodically collects and **permanently preserves** the public footprint of a
set of North American asset managers — Burgundy, Mawer, EdgePoint, Beutel
Goodman and Letko Brosseau — each tracked independently:

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

## Tracking several managers

Every snapshot table carries a `manager_id`, and every uniqueness rule is scoped
to it — `aum_history` is keyed on `(manager_id, as_of_date, source)`, so two
managers reporting the same quarter cannot overwrite each other.

Add a manager by appending to `config.MANAGERS`; `pipeline.run` syncs the
registry each pass. A CIK is taken from that filer's own EDGAR documents rather
than guessed: the wrong ten digits would fill the dashboard with another firm's
portfolio and still look healthy. Config is authoritative, so correcting a CIK
there fixes the tracked filer on the next run.

A manager missing what a collector needs — no CIK, no CRD, no website URL, no
DART search terms — is skipped for that collector, not guessed at:

```bash
python -m pipeline.backfill --since 2015 --manager mawer   # one manager
python -m pipeline.backfill --since 2015                   # all of them
python -m pipeline.reparse --manager burgundy
```

The dashboard takes `?manager=<slug>`; the header picker switches between them.

## Layout

```
config.py            # MANAGERS registry (CIK, CRD, URLs, DART terms) + shared constants
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
above. Each service reads its own config-as-code file, so their start commands
don't collide:

| Service | Config file | Start command | Setting |
|---|---|---|---|
| `dashboard` | `railway.json` (default) | `python -m db.migrate && uvicorn dashboard.app:app --host 0.0.0.0 --port $PORT` | always on |
| `collector` | `railway.collector.json` | `python -m db.migrate && python -m pipeline.run` | Cron `0 22 * * *` (UTC 22:00 = KST 07:00, daily) |

Steps:
1. Create a Railway project from this repo and add the **PostgreSQL** plugin.
2. Service **dashboard** deploys automatically from `railway.json`. Generate a
   domain for it under Settings → Networking.
3. Add a second service **collector** from the same repo. In its
   Settings → Config-as-code, set the **Railway Config File** path to
   `railway.collector.json` — that file supplies the start command and cron
   schedule, so no manual entry is needed. Do **not** expose a domain for it.
4. Give both services the env vars above (`DATABASE_URL` as a reference to the
   Postgres plugin, `SEC_USER_AGENT`, `DART_API_KEY`, …).

### One-shot maintenance runs

The collector is a cron service, so it only runs on schedule. To run something
once immediately, point the collector service's **Config File** at one of these
(they omit the cron schedule, so Railway runs them once on deploy, then the
process exits), then switch back to `railway.collector.json`:

- `railway.backfill.json` — `pipeline.backfill` (loads historical 13F filings, then heals each manager's `13f_total` AUM series so a backfilled manager is complete without waiting for the nightly run).
- `railway.reparse.json` — `pipeline.reparse` (rebuild snapshots/derived rows from stored raw docs without re-fetching; e.g. to backfill the `13f_total` AUM series after a parser change).

Because the start command is fixed, the backfill takes its options from
environment variables — set them on the service, no extra config file per
manager:

| variable | default | meaning |
|---|---|---|
| `BACKFILL_MANAGER` | `all` | manager slug to load, or `all` |
| `BACKFILL_SINCE` | `2013` | earliest report year |
| `BACKFILL_LIMIT` | unset | max filings per manager this run |

So a newly added manager is loaded by setting `BACKFILL_MANAGER=mawer` and
deploying once. Backfilling is idempotent, so re-running costs nothing but
time; each manager is independent, and one failing does not stop the rest —
the run exits non-zero and names who failed. Leaving `BACKFILL_MANAGER` unset
loads every tracked manager, which is the slower first-time path (SEC requests
are rate-limited to under 10/s).

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
- **Reporting transition (Q4 2025):** Burgundy switched from filing its own 13F-HR
  (Holdings Report) to filing 13F-NT (Notice); its US holdings are now reported by
  **Bank of Montreal** on the combined filing. The collector records these notices
  in `filing_notices` and the dashboard shows a banner explaining the change. A
  combined 13F cannot be split back into Burgundy's slice, so standalone US
  holdings — and the derived `13f_total` AUM series — end at 2025-09-30. AUM from
  Form ADV RAUM (CRD 114317) and the website is filed independently and keeps
  updating.
