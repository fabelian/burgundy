# Finding these managers' Korean holdings

## What this is for

The goal is **institutional sales prospecting**, not portfolio analytics: find how much
of 삼성전자 / SK하이닉스 and similar large caps the tracked managers hold, so research
can be offered and order flow won. That makes two things matter more than they would
otherwise:

- **Large caps specifically.** A source that only surfaces small caps is worthless here.
- **Freshness.** Near-real-time preferred; annual disclosure is too slow to act on.

The tracked set is fixed at the five managers in `config.MANAGERS` — Burgundy, Mawer,
EdgePoint, Beutel Goodman, Letko Brosseau. Expanding the list is out of scope.

## Sources ruled out, and why

Each of these was investigated and rejected on evidence, not preference. Recording it
so the same ground is not covered twice.

### DART 대량보유상황보고 (5% rule) — structurally incapable

The 5% threshold is a **percentage of the issuer**, so the disclosure exists only where a
manager owns a large slice of a small company. Samsung Electronics' market cap puts 5%
in the tens of trillions of won — larger than these managers' entire equity books. The
rule therefore surfaces *exactly the opposite* of what is wanted: the Korea tab filled
with small caps like 오성첨단소재 and can never show a large cap.

The collector is kept as a cheap safety net (a few days' lookback per daily run) in case
a real 5% position ever appears. The multi-year backfill was abandoned — see
"Operational notes".

### Korean sources generally — no per-manager disclosure exists

KSD, FSS and KRX publish foreign ownership **in aggregate only**. The sole places an
individual foreign manager is named are the 5% rule above and short-interest disclosure
(0.5%, irrelevant for long-only). There is no Korean route to this data.

### 13F Korean ADRs — excluded by the user

13F covers US-exchange-traded securities. Korean exposure appears only through ADRs
(KB, SHG, PKX, SKM, KT, KEP, LPL, WF, GRVY). Samsung Electronics and SK Hynix have no
US listing, so they never appear. Ruled out.

### Annual proxy voting records (NI 81-106) — too slow

Canadian funds must publish, annually for the period ending 30 June, every meeting they
voted — including foreign issuers, with tickers. A vote at Samsung's AGM proves the
holding. But the lag reaches 14 months, which fails the freshness requirement. Ruled out.

### SEC Form N-PORT — these managers do not file it

N-PORT would be ideal: month-end position level, ISIN, structured XML, free. It applies
to **US-registered** funds only, and none of the five have one that could hold Korean
equity:

| Manager | US registered fund | N-PORT | Korean equity |
|---|---|---|---|
| Mawer | US vehicles are **private funds** | no | — |
| Beutel Goodman | sub-advises a Brown Advisory fund | yes | no — **US large-cap value** mandate |
| EdgePoint | none found | no | — |
| Letko Brosseau | none found | no | — |
| Burgundy | none found | no | — |

Building an N-PORT collector for this manager set would return nothing.

## What does work: the managers' own fund disclosures

Confirmed by example: **Mawer International Equity Fund holds Samsung Electronics at
1.7%**, published in its quarterly fund PDF:

```
.../mawer-com-cms/assets/funds/2q24-mawer-international-equity-fund-series-a.pdf
```

Korean positions can only sit in **International / Global / Emerging Markets** mandates —
Canadian and US-only funds can be skipped. Cadence is quarterly for Mawer, monthly for
some managers: slower than "real time", but far fresher than anything else that contains
a Korean large cap at all.

For genuine near-real-time, the only routes are commercial shareholder-surveillance
(S&P Global/Ipreo, Nasdaq IR, LSEG), which work from custodial settlement data rather
than disclosure, or an issuer's own 실질주주명부 via an IR relationship. Both are outside
this repo.

## What is built

1. **`funds` + `fund_holdings`** (migration `004`). `funds` is the registry of which
   mandates are worth reading; `fund_holdings` holds manager, fund, as-of date, security,
   weight and country. Two columns exist to stop a specific wrong conclusion:

   - `disclosure_scope` (`top_n` / `full`) — most fact sheets print only the top ten.
     A manager not shown holding Samsung has **not** been shown to be absent from it, and
     the tab says so rather than letting silence read as "does not hold".
   - `is_korean` — classified on write by `parsers.securities.is_korean`, not by a `LIKE`
     over names at read time. `FundHoldingRow` fills it for every row that reaches the
     database, so no future parser can insert a Samsung position the tab then misses.

   Fact sheets carry no CUSIP, so identity is `security_key` — the normalised printed
   name. A share class stays in the key (a fund can hold the common and the preferred at
   once); legal suffixes do not (`POSCO Holdings Inc.` and `POSCO` are one position).

2. **`collectors/factsheet.py`** — downloads each tracked fund's PDF and stores it in
   `raw_documents` (base64; layer 1 keeps the original bytes). Registered in
   `pipeline.run` as a **weekly** collector: fact sheets are quarterly, so a daily fetch
   would re-request the same unchanged PDF six times.

   Managers publish in two shapes and the dedup rule differs between them:

   | | `doc_url_template` | `doc_url` |
   |---|---|---|
   | path | period is in it (`2q24-…`) | fixed; contents replaced each quarter |
   | reaches | past quarters — the only route to a trend | latest only |
   | `external_id` | `fund:period` | **none** |

   The `external_id` distinction is not cosmetic. Keyed by one, a fixed URL would be
   marked seen on its first fetch and every later quarter skipped forever; with none,
   dedup falls to the content hash, so the document is re-read each run and only a
   genuinely new edition is stored — the same rule the DART collector uses.

   Mawer offers both: the per-quarter path recorded above, and a CDN asset
   (`az-prd-mawer-com-cms-….azurefd.net/…/Mawer_International_Equity_Fund_Series_F_….pdf`)
   carrying no period at all. Series differ in fees, not holdings, so either answers the
   Korean question.

3. **The Korea tab**, rebuilt on `fund_holdings`. It is deliberately the one view that is
   *not* scoped to the selected manager — the question is which of the five holds Samsung
   and at what weight, and that is a comparison. Coverage is shown above the holdings so
   an empty table can be read correctly: a fund with no document collected is *unknown*,
   not empty. The DART section survives below, labelled as the safety net it is.

## What remains

**The fact-sheet parser is not calibrated.** `parsers.parse_factsheet.parse_factsheet`
raises `FactsheetFormatUnknown` rather than guessing a layout — writing one blind is how
the DART sweep went wrong: it ran clean, filled the Korea tab, and every row in it was
the wrong kind of company. The collector still runs, and that is the point: it fetches
and keeps the document, which is what calibration needs.

The sandbox has **no outbound network at all** — `example.com`, `sec.gov`, `mawer.com`
and the Azure CDN all fail identically (proxy `403` at CONNECT, i.e. policy denial rather
than a site-side block), so this is not an allowlist that happens to omit one host, and a
fresh session does not fix it. Two ways forward, either is enough:

- upload one Mawer International Equity fact sheet into the session, or
- let the collector run in production and read the stored PDF back out of
  `raw_documents` (`source = 'factsheet'`).

`describe()` and `pdf_text()` in that module are already written and format-independent;
they report page count and whether a text layer exists, which is what decides between a
text parser and OCR. `parse_factsheet` then needs to return, per printed position: name,
weight, country when the sheet has the column, the stated as-of date, and whether the
list is the whole portfolio or only the top N.

**The other four managers have no funds registered.** `config.FUNDS` holds only Mawer
International Equity, whose document path is the one confirmed by observation. A fund is
added once its URL has been *seen*, never guessed — the same rule the CIKs follow. An
invented template would 404 quietly on every run and read as "this manager discloses
nothing", which is indistinguishable from a real absence.

## Operational notes

- **The collector service picks its job from a config file.** `railway.collector.json` is
  the daily cron; `railway.backfill.json`, `railway.backfill_kr.json`, `railway.heal.json`
  and `railway.reparse.json` are one-shot jobs. Whichever is selected runs on *every*
  deploy.
- **Merging to main redeploys the collector**, which restarts whatever that config runs.
  A long backfill was killed twice this way. Switch the config file back before merging.
- The Korean sweep now **refuses to start without an explicit `--since` /
  `KR_BACKFILL_SINCE`**, so it can no longer restart itself on an unrelated deploy.
- The fact-sheet collector reports `new_raw > 0` with `new_rows = 0` until the parser is
  calibrated. That is the expected state, and it is visible on the dashboard's collector
  panel — it is not the same signal as a quiet period, where `new_raw` is 0 too.
- Local development needs a database: there is no Postgres running in a fresh sandbox and
  the DB-backed tests silently `skip` without one. `initdb` under `/var/lib/postgresql`
  (not the scratchpad — the `postgres` user cannot traverse it) and point `DATABASE_URL`
  at the socket to get the full suite running instead of half of it.
