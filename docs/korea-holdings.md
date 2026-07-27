# Finding these managers' Korean holdings

## What this is for

The goal is **institutional sales prospecting**, not portfolio analytics: find how much
of 삼성전자 / SK하이닉스 and similar large caps the tracked managers hold, so research
can be offered and order flow won. That makes two things matter more than they would
otherwise:

- **Large caps specifically.** A source that only surfaces small caps is worthless here.
- **Freshness.** Near-real-time preferred; annual disclosure is too slow to act on.

The tracked set is `config.MANAGERS`. It began as five Canadian managers — Burgundy,
Mawer, EdgePoint, Beutel Goodman, Letko Brosseau — and **DRZ and Kopernik were added
later**. Everything below about ruled-out sources was reasoned against the Canadian five;
the two US advisers change some of those answers, and that is set out in
"US-domiciled managers" below.

Neither new manager's identifiers have been confirmed yet, so both are registered with a
name and nothing else. Every collector skips them until a CIK or CRD is read off that
filer's own documents — the same rule the original five follow, and the reason a wrong
CIK has never put another firm's portfolio on this dashboard.

## The measurement ceiling

Every free source here is an **extract**, not a portfolio, and that is the property that
decides what this system can and cannot claim. Measured on the calibration document
(Mawer International Equity, 30 June 2026):

| | |
|---|---|
| Fund size | $7,251.5M |
| Holdings | 72 — of which **24 printed, 48 not** |
| Printed | 53.8% of the fund |
| **Not printed** | **41.3% = $2,995M across 48 positions** |
| **Visibility floor** | **1.6% = $116M** |
| Korean, confirmed | 5.8% = $421M (SK hynix 3.0, Samsung Electronics 2.8) |

Two consequences, and the second is the useful one:

- A Korean position **below ~$116M is invisible**, and no amount of parsing recovers it.
  What this system reports is therefore a **lower bound on presence**, never a portfolio
  and never an absence.
- But an unprinted position **cannot exceed the smallest printed one** — it would have
  ranked into the list otherwise. So "they hold $500M of Samsung and we missed it" is
  excluded by construction. The blind spot has a known size.

Say the bound, never the absence. `disclosure_scope` carries this into the schema and the
Korea tab states it in words; the discipline only fails if someone reads a blank cell as
a zero.

A second, wider ceiling cuts across every free source: **pooled funds and segregated
institutional mandates disclose nothing publicly at all.** Fact sheets, MRFP, Fund Facts
and proxy voting records all cover published funds only. Several of these managers reach
Korean equity precisely through vehicles none of them touch.

## Source comparison

The whole landscape in one place, so a vendor conversation or a re-derivation starts here
rather than from scratch. "Ceiling" is the column that matters — freshness is worth
nothing on a source that structurally cannot show a large cap.

| Source | Ceiling | Freshness | Vehicles reached | Cost | Status |
|---|---|---|---|---|---|
| **Fund fact sheets** | top 10–25 | quarterly / monthly | published funds | free | **built** |
| SEDAR+ **MRFP** | top 25 | semi-annual | prospectus mutual funds | free | manual retrieval |
| SEDAR+ **Fund Facts** | top 10 | annual | prospectus mutual funds | free | manual retrieval |
| **Proxy voting** (NI 81-106) | **none** | ~14-month lag | reporting-issuer funds | free | complement — see below |
| **Ownership databases** (Morningstar Direct, Fundata, FactSet, LSEG, Bloomberg) | **unknown — decisive** | monthly | prospectus mutual funds | ~$10–25k/user/yr | unverified |
| **Shareholder surveillance** (S&P Global/Ipreo, Georgeson, Morrow Sodali, CMi2i) | none | near-real-time | all | ~$30–100k/yr | issuer-side product |
| 실질주주명부 via issuer IR | none | record date | all | IR relationship | out of scope |
| DART 5% (대량보유) | large caps impossible | days | n/a | free | ruled out |
| **SEC N-PORT** | **none** | monthly | US-registered funds | free | none of the Canadian five file — **re-open for DRZ / Kopernik** |
| 13F | US-listed only | quarterly | US positions | free | ruled out for Korea; applies to the US advisers |
| KSD / FSS / KRX | no per-manager breakdown | daily | n/a | free | ruled out |

Cost figures are order-of-magnitude and **unverified** — this sector consolidates often
and they may be stale. Confirm before budgeting.

## Sources investigated and set aside

Each of these was rejected on evidence, not preference. Recording it so the same ground is
not covered twice — **and so a rejection can be revisited when the reasoning behind it
changes.** One already has: proxy voting records were ruled out on freshness alone, and
quantifying the measurement ceiling turned them into the most valuable source left.

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

### Annual proxy voting records (NI 81-106) — reclassified: a complement, not a primary

Canadian funds must publish, annually for the period ending 30 June, every meeting they
voted — including foreign issuers, with tickers. A vote at Samsung's AGM proves the
holding. The lag reaches 14 months, which fails the freshness requirement, and on that
basis this was originally ruled out.

That judgment was wrong to be final, and the reason only became visible once the
measurement ceiling above was quantified: **a voting record has no top-N ceiling.** It
lists every meeting voted, so a 0.3% position appears exactly as a 3% one does. It is the
only free source that reaches below the ~$116M floor.

The two sources fail in opposite directions, which is what makes them a pair:

| | Fact sheet | Proxy voting record |
|---|---|---|
| Freshness | quarterly | ~14 months stale |
| Coverage | **top 10–25 only** | **every position voted** |
| Size disclosed | yes | no |

Read together they answer more than either does alone:

- in **both** → held, and sized
- in the voting record, **not** the fact sheet → held, but **under ~$116M** — the band
  this system is otherwise blind to
- in **neither** → the closest thing to evidence of absence that free data allows

For the sales question "does this manager hold Samsung at all", the stale source is the
better one. Not built; the highest-value remaining source. Same vehicle limit as MRFP —
pooled and segregated mandates file nothing.

### SEC Form N-PORT — none of the *Canadian five* file it

> **Re-open for DRZ and Kopernik.** This section reasons about the original five only.
> Both new managers are US advisers, and a US-registered fund would make N-PORT available
> — with no top-N ceiling at all. See "US-domiciled managers".

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

## US-domiciled managers — the ruled-out sources are worth re-asking

DRZ (Winter Park, FL) and Kopernik (Tampa, FL) are **US advisers**, and three of the
rejections above were reasoned specifically about Canadian firms. For these two:

- **13F applies.** Their US-listed holdings are disclosed quarterly, position level, free,
  with a stable API. It still cannot show Samsung Electronics or SK Hynix, which have no
  US listing — the ADR limit stands — but it is a real source where it was previously
  "these managers do not file".
- **N-PORT may apply, and it has no top-N ceiling.** It was ruled out because none of the
  five Canadian managers has a US-registered fund that could hold Korean equity. Kopernik
  appears to run its global all-cap strategy as a **US-registered fund** — a soft close is
  a mutual-fund event — and if so, N-PORT gives **month-end, position-level, whole
  portfolio, ISIN, structured XML, free**.

  That would be strictly better than everything built here: no ~$116M floor, no top-25
  extract, no PDF layout to calibrate, monthly rather than quarterly. **Check this before
  chasing fact sheets for Kopernik.** Search EDGAR for the fund, not the adviser: N-PORT
  is filed by the registered fund or its trust, so an adviser-name search can miss it.
- **Form ADV** applies to both once a CRD is known, giving official RAUM.

DART and the Korean-sources reasoning are unaffected — those are properties of Korean
disclosure, not of where the holder is domiciled.

## Commercial data — one question decides whether it is worth buying

Two product categories get conflated, and only one is sold in the direction this needs:

| | **Surveillance** | **Ownership database** |
|---|---|---|
| Answers | "who owns **my** stock" | "who owns **this** stock" |
| Sold to | issuer IR departments | anyone |
| Built from | custodial / settlement data | filings and fund holdings |
| Vendors | S&P Global (Ipreo), Georgeson, Morrow Sodali, CMi2i | FactSet, LSEG, Morningstar, Bloomberg |

Surveillance is the technically complete answer and it is **not the product for us** — it
is bought by Samsung Electronics to learn who its holders are, not by a third party to
profile five managers. Korea also weakens it: US surveillance anchors on 13F, and Korea
has no equivalent anchor, leaving 실질주주명부 — issuer-only — as the authoritative route.

Ownership databases are purchasable, but most **aggregate the same disclosures already
parsed here**, which buys convenience and inherits the ceiling unchanged. One exception
would not:

> **Fund companies supply data vendors with full portfolio holdings, even though the
> regulatory document prints only the top 25.** If Morningstar Direct or Fundata carries
> complete Canadian mutual fund holdings, the ~$116M floor disappears — Mawer's 48
> unprinted positions and $2,995M become visible.

That is the one question to ask, and it is answerable free on a sales trial:

**"For Canadian mutual funds, do you carry the complete portfolio, or the MRFP top 25?"**

- **Complete** → the ceiling is a purchasing decision, not a data-availability one, and
  this becomes the highest-value spend on the list.
- **Top 25** → the commercial route buys convenience only. Proxy voting records, free and
  with no ceiling at all, are then the better investment.

Either answer leaves pooled and segregated mandates untouched.

Integration is cheap and already accounted for: a vendor feed is one more collector
writing `fund_holdings` with `disclosure_scope = 'full'`. The schema, the Korea tab and
the top-N warning need no changes — the warning simply stops firing.

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

   `cadence` must be one of the modelled ones — `monthly` / `quarterly` /
   `semi-annual` / `annual`. An unmodelled value raises rather than falling back to
   quarterly: quartering a semi-annual MRFP would look for Q1 and Q3 documents that were
   never filed and date the ones that exist to a period they do not cover. The failure is
   isolated to the fund, so one mistyped cadence cannot blind a manager's other funds.

   The `external_id` distinction is not cosmetic. Keyed by one, a fixed URL would be
   marked seen on its first fetch and every later quarter skipped forever; with none,
   dedup falls to the content hash, so the document is re-read each run and only a
   genuinely new edition is stored — the same rule the DART collector uses.

   Mawer offers both: the per-quarter path recorded above, and a CDN asset
   (`az-prd-mawer-com-cms-….azurefd.net/…/Mawer_International_Equity_Fund_Series_F_….pdf`)
   carrying no period at all. Series differ in fees, not holdings, so either answers the
   Korean question.

3. **The Korea tab**, rebuilt on `fund_holdings` and **scoped to the selected manager**
   like every other tab. Coverage is shown below the holdings so an empty table can be
   read correctly: a fund with no document collected is *unknown*, not empty. The DART
   section survives at the bottom, labelled as the safety net it is.

   It was briefly cross-manager, on the reasoning that "which of the five holds Samsung"
   is a comparison and paging through five tabs to answer it is absurd. That was wrong in
   practice: the manager column is the first thing a narrow screen scrolls out of view,
   and production showed Mawer's Samsung position sitting under a heading that said
   Burgundy. **A misattributed holding is a worse failure than an extra click** — it is
   the one error that would put a salesperson on a call about a position the firm does
   not have.

   A separate "다른 운용사" card excluding the selected manager was tried as a middle
   ground and then removed too: the tab is read one manager at a time, and another firm's
   holdings on the page were noise at best. **The manager picker is the comparison.**

   The rule that survives both attempts generalises: when a column is what makes a row's
   meaning correct, it cannot live in a table that scrolls — and the cheaper fix is
   usually to remove the rows that need it rather than to defend the column.

4. **`parsers/parse_factsheet.py`** — calibrated against the Mawer International Equity
   Fund (Series F) sheet as at 30 June 2026. Its extracted text is checked in at
   `tests/fixtures/mawer_international_equity_series_f.txt`.

   What the real document dictated:

   - The block is headed `Top 25 Holdings % Weight` and **appears twice**, once per
     printed column, then ends at `Total 58.7`. Restarting at the second header drops
     the first twelve positions.
   - Equity Sector Weights and Region Weights sit higher on the same page in the
     identical `Name 12.3` shape. A block anchored one heading early parses cleanly and
     silently reports a portfolio of sectors.
   - **There is no per-security country column.** Korean identification falls entirely to
     the name rules in `parsers/securities.py` — that list is load-bearing, not a nicety.
   - `Cash and Cash Equivalents` is printed inside the list and counted in the total. It
     is checked, then dropped: it is not a position and must not rank as one.
   - `Number of Holdings: 72` against 25 listed is what proves the list is an extract.

   Two anti-silence rules, because the failure that matters is a plausible empty answer
   rather than a crash — "holds nothing Korean" is a sentence someone acts on:

   - every anchor is required; a redesigned sheet raises rather than returning `[]`.
   - the parsed weights are checked against the document's **own printed total**. A
     dropped or spurious row parses perfectly well; only the sum gives it away.

   Result on the calibration document: 24 securities, of which **SK hynix 3.0%** and
   **Samsung Electronics 2.8%** — 5.8% Korean, with no foreign holding wrongly claimed.
   Note the sheet prints `SK hynix Inc`, not `SK Hynix`, which the normalised key handles.

   Extracted PDF text also carries **non-breaking spaces** (U+00A0) inside bracketed
   labels. Patterns written against plain spaces silently match nothing there; the
   security key normalises them away via NFKC, so stored names are unaffected.

5. **`fund_snapshots`** (migration `006`) — what the document says about the *fund*.
   A weight alone is not an answer: "3%" only means something against the fund it is 3%
   of, and the sheet states that figure. With it kept, 3.0% of Mawer International Equity
   becomes **≈C$218M**, which is the number a sales conversation turns on. The tab shows
   the fund's size and the implied amount beside every weight.

   The NAV must be read carefully — the sheet prints three similar figures in a row:

   ```
   Fund Net Asset Value (Series F, O, S):   $7,251.5 million   <- the fund
   Total Net Asset Value (Series F):          $843.3 million   <- one series
   Net Asset Value Per Unit:                      $103.55      <- per unit
   ```

   Matching `Net Asset Value` loosely takes whichever comes first, and every weight on
   the tab is then read against a denominator that is wrong by 8.6× or by six orders of
   magnitude. The pattern is anchored to the line start and to the word `Fund`. Currency
   comes from the fund registry, not from the `$` — the symbol does not say which dollar.

   Also kept is `total_holdings` (72), previously read to decide `disclosure_scope` and
   discarded. The coverage table now shows **24 / 72**, so how much of the portfolio is
   *not* on screen is visible rather than merely warned about.

5. **`proxy_votes`** (migration `005`) and the **evidence view** behind the Korea tab.
   A voting record has no top-N ceiling and no weight; a fact sheet is the reverse.
   Joined, they separate three states that look identical in either source alone:

   | | Fact sheet | Voting record | Reading |
   |---|---|---|---|
   | `sized` | yes | yes | held, and measured |
   | `unsized` | — | yes | **held, below the fact sheet's floor** |
   | `recent` | yes | — | held; the record lags ~14 months |

   `unsized` is the band this repo was otherwise blind to, and the reason the source is
   worth building. `recent` is deliberately *not* flagged as suspicious: a position opened
   since the record's period is legitimately absent from it.

   The join is keyed on `(fund_id, security_key)`. The fund matters because NI 81-106
   makes the record a fund-level obligation, so a fund's sheet and that same fund's record
   describe one portfolio — keying on the manager would fold two of its funds holding
   Samsung into a single row and lose a position. `security_key` is what lets a vote for
   `SK Hynix Inc.` meet a holding printed `SK hynix Inc` without either being rewritten.

   Votes are stored **one row per meeting, not per ballot item**. The evidence is "this
   fund held this issuer on this date"; twenty resolutions would say that twenty times,
   and dedup would then hinge on matching free-text resolution titles across documents.

## SEDAR+ — a second document source, but not an automatable one

The attraction is real: **MRFP** (Management Report of Fund Performance, NI 81-106)
carries a "Summary of Investment Portfolio" listing the **top 25 holdings** — the same
depth as the Mawer fact sheet — and **Fund Facts** carries the top 10. Both are regulated
formats, so one parser plausibly covers all four remaining managers instead of four
site-specific ones. Cadence is semi-annual, slower than a quarterly fact sheet but well
inside what this is for.

Two things stop it being the clean sweep it looks like, and both matter before anyone
builds toward it:

- **SEDAR+ is not EDGAR.** EDGAR publishes stable, documented JSON (`data.sec.gov`) with
  permanent archive paths, which is why `edgar_13f` can discover filings unattended.
  SEDAR+ has a search UI over POST endpoints and hands out session-scoped document links;
  there is no documented public API and no stable per-filing URL to build a template
  from. Discovery there would have to be written against undocumented endpoints — the
  same blind-target problem as an invented fact-sheet URL, one layer up. Not attempted.
- **Only prospectus-offered mutual funds file MRFP at all.** Pooled funds and segregated
  institutional mandates do not, and several of these managers reach Korean equity
  precisely through those. A manager absent from SEDAR+ has therefore disclosed nothing
  *there* — it is not evidence about the manager.

What SEDAR+ **is** good for: obtaining documents by hand. An MRFP retrieved from the
search UI drops straight into the existing path — register the fund with `cadence:
"semi-annual"`, add its layout to `parse_factsheet_text`, done. The collector, schema and
Korea tab need no changes to accept one.

## What remains

**The other four managers have no funds registered.** `config.FUNDS` holds only Mawer
International Equity, whose document paths are the ones confirmed by observation. A fund
is added once its URL has been *seen*, never guessed — the same rule the CIKs follow. An
invented URL would 404 quietly on every run and read as "this manager discloses nothing",
which is indistinguishable from a real absence.

**The parser is calibrated against one manager's layout.** Mawer's is now known; the
other four will differ, and each will need its own calibration against a real document.
`parse_factsheet_text` is the seam to extend, and the anti-silence rules mean an
uncalibrated layout fails loudly instead of reporting an empty portfolio.

**No voting record has been collected yet.** The table, the classification and the tab are
built and tested; what is missing is a collector, and it is gated on the same two things
as everything else here — a **document URL that has been seen** and a **layout observed
against a real file**. Neither exists yet for any of the five, and both were guessed at
exactly zero times in this repo, which is why the DART mistake has not repeated.

Under NI 81-106 the record is posted on the fund's own website (not filed to SEDAR+), so
the URLs sit alongside the fact sheets already being hunted — collect both in one pass.
Once a document is in hand the shape is known from the regulation rather than guesswork:
issuer, meeting date, ballot item, and how the fund voted. Only the *layout* needs a file.

**The sandbox has no outbound network at all** — `example.com`, `sec.gov`, `mawer.com`
and the Azure CDN all fail identically (proxy `403` at CONNECT, i.e. policy denial rather
than a site-side block), so this is not an allowlist omitting one host, and a fresh
session does not fix it. To calibrate another manager, either upload its fact sheet into
the session, or let the collector run in production and read the stored PDF back out of
`raw_documents` (`source = 'factsheet'`). `describe()` reports whether a text layer
exists, which is what decides between a text parser and OCR.

## Operational notes

- **The collector service picks its job from a config file.** `railway.collector.json` is
  the daily cron; `railway.backfill.json`, `railway.backfill_kr.json`, `railway.heal.json`
  and `railway.reparse.json` are one-shot jobs. Whichever is selected runs on *every*
  deploy.
- **Merging to main redeploys the collector**, which restarts whatever that config runs.
  A long backfill was killed twice this way. Switch the config file back before merging.
- The Korean sweep now **refuses to start without an explicit `--since` /
  `KR_BACKFILL_SINCE`**, so it can no longer restart itself on an unrelated deploy.
- A fact-sheet run showing `new_raw > 0` with `new_rows = 0` means the document was
  fetched but its layout was not recognised — expected for a manager not yet calibrated,
  and visible on the dashboard's collector panel. It is not the same signal as a quiet
  period, where `new_raw` is 0 too. The reason — which anchor failed, and the document's
  page/character counts — is printed to the run log, and the PDF itself is kept in
  `raw_documents` to calibrate against.
- Local development needs a database: there is no Postgres running in a fresh sandbox and
  the DB-backed tests silently `skip` without one. `initdb` under `/var/lib/postgresql`
  (not the scratchpad — the `postgres` user cannot traverse it) and point `DATABASE_URL`
  at the socket to get the full suite running instead of half of it.
