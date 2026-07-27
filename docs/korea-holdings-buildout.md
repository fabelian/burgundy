# Korea holdings build-out — work record

July 2026. What was built, what was decided, what was decided *again*, and what is left.

`korea-holdings.md` is the reference: it argues which sources can and cannot answer the
question, and it is the document to read before proposing a new one. **This file is the
history** — the order things happened in, and which judgments were overturned by evidence.
Read it to avoid re-deriving a conclusion that has already been reversed once.

---

## The problem

The Korea tab was built on DART **대량보유상황보고** (5% disclosures). That threshold is a
percentage of the *issuer*, and 5% of Samsung Electronics exceeds these managers' entire
equity books — so the rule can only ever surface small caps, which is the opposite of what
institutional prospecting needs. The tab was filled with names like 오성첨단소재 and could
never show a large cap.

The managers' own **fund fact sheets** are the only free route to a Korean large cap for
this manager set. Everything below follows from that.

---

## What was built

| Component | Purpose |
|---|---|
| `funds`, `fund_holdings` (migration `004`) | Which mandates are worth reading, and the positions themselves |
| `fund_snapshots` (`006`) | The fund's own NAV per period — what a weight is a percentage *of* |
| `proxy_votes` (`005`) | NI 81-106 voting records: the only free source with no top-N ceiling |
| `collectors/factsheet.py` | Fetches fund PDFs; handles both URL shapes managers publish |
| `parsers/parse_factsheet.py` | Calibrated against a real Mawer sheet; fixture checked in |
| `parsers/securities.py` | Normalised security identity + Korean classification |
| Korea tab | Rebuilt on all of the above, scoped to one manager |

**Result on the calibration document** (Mawer International Equity, 30 June 2026):
24 securities parsed, of which **SK hynix 3.00% (≈C$217.5M)** and **Samsung Electronics
2.80% (≈C$203.0M)** — with no foreign holding wrongly claimed as Korean.

---

## Decisions that were reversed

The useful part of this record. Each was a considered judgment, and each was wrong.

### 1. The Korea tab was cross-manager

**Reasoning:** "which of the five holds Samsung" is a comparison; making someone click
through five tabs to answer it is absurd.

**What broke it:** a production screenshot showed the **Burgundy** heading above **Mawer's**
Samsung and SK hynix positions. The manager column is the first thing a narrow screen
scrolls out of view, and once it is gone the rows read as belonging to whoever the picker
names. A misattributed holding puts a salesperson on a call about a position the firm does
not have, and no warning text elsewhere on the page undoes it.

**Now:** scoped to the selected manager, and the manager column is *removed* rather than
deprioritised. A column that must be read for a row to mean the right thing cannot live in
something that scrolls.

### 2. A peer-comparison card replaced it

Added as a middle ground so the comparison did not vanish outright — a card listing the
*other* managers, where every row belongs to someone else by construction.

**What broke it:** in use it earned nothing. The tab is read one manager at a time, and
another firm's holdings under the one you are looking at are noise at best. **The manager
picker is the comparison.** Removed, with a test that nothing belonging to another manager
appears on the page at all.

### 3. Proxy voting records were "too slow — ruled out"

**Reasoning:** the lag reaches 14 months, which fails the freshness requirement.

**What broke it:** quantifying the measurement ceiling. A fact sheet prints the top 10–25
positions, so it cannot show a Korean holding below its smallest printed weight — about
**$116M** on the calibration document, with **41.3% of the fund ($2,995M across 48
positions) invisible**. A voting record has *no such ceiling*: it lists every meeting
voted, so a 0.3% position appears exactly as a 3% one does.

The two fail in opposite directions, which is what makes them a pair:

| | Fact sheet | Voting record |
|---|---|---|
| Freshness | quarterly | ~14 months stale |
| Coverage | **top 10–25 only** | **every position voted** |
| Size | yes | no |

Read together they separate "held, under $116M" from "not held" — which neither does
alone. **Reclassified from ruled-out to the highest-value unbuilt source.**

### 4. N-PORT — "these managers do not file it"

True of the five Canadian managers, and stated without that qualifier. Adding two **US
advisers** reopened it: 13F applies to them, and a US-registered fund would bring N-PORT,
which has no top-N ceiling at all.

**Caveat found while writing the check procedure:** "month-end" was an overstatement.
N-PORT is *filed* monthly but historically only the third month of each quarter became
public, 60 days later; 2024 amendments moved toward monthly publication with staggered
compliance. **N-PORT's win is completeness, not freshness** — each public report is the
whole portfolio.

### 5. "A fund with no document URL is unreadable"

Asserted in a test when the only registered fund was Mawer's. The real rule forbids
*guessed* URLs — an invented template 404s quietly on every run and reads as "this manager
discloses nothing". A **blank** URL is a different thing: inert but *visible*, appearing on
the coverage card as 미수집. Inert and honest, versus inert and misleading.

---

## The shape underneath all of them

Every reversal above, and most of the bugs, are the same failure: **an absence reading as a
conclusion.**

- a top-25 extract reading as a full portfolio → "does not hold"
- an unsynced registry reading as an unconfigured one → "no funds tracked"
- a fixed URL marked seen on first fetch → later quarters skipped forever, looking like a
  manager that stopped publishing
- a parser returning `[]` on an unrecognised layout → "holds nothing Korean"
- a semi-annual filing quartered → dated to a period it does not cover
- an EDGAR search under the adviser CIK → "no N-PORT", when the fund files under its own

The countermeasures are consistent and worth keeping:

1. **Say the bound, never the absence.** `disclosure_scope` carries the top-N caveat into
   the schema; the tab states it in words.
2. **Distinguish "unknown" from "empty" in the UI.** Coverage sits above the holdings so a
   fund with no document read is *unknown*, not empty.
3. **Fail loudly rather than returning nothing.** Every parser anchor is required; a
   redesigned sheet raises instead of returning `[]`.
4. **Check the parse against the document's own arithmetic.** Parsed weights are compared
   with the printed `Total` — a dropped or spurious row parses perfectly well, and only the
   sum gives it away.
5. **Never guess an identifier.** A blank makes a collector skip, visibly. A wrong CIK
   shows another firm's portfolio and looks entirely normal.

---

## Current state

### Managers

| Manager | Status | CIK | Collects |
|---|---|---|---|
| Burgundy | active | `0001315868` | 13F, Form ADV, website ×2 |
| DRZ (DePrince, Race & Zollo) | active | `0001008894` | 13F |
| Kopernik (Kopernik Global Investors) | active | `0001599814` | 13F, website AUM |
| Mawer, EdgePoint, Beutel Goodman, Letko Brosseau | **retired** | on file | nothing |

Retiring is `is_active=False` — one flag that both stops outbound collection
(`pipeline.run` iterates `active()`) and removes the manager from the dashboard (every tab
resolves through it). A hand-typed `?manager=mawer` falls back rather than serving their
data. Nothing collected is deleted, so it is reversible.

> **The retirement took the Korean data with it.** Mawer was the only manager with a
> document URL on file, so the calibrated fact sheet is no longer reachable from the tab.
> The pipeline is intact and still passes against its checked-in fixture; it has no active
> manager feeding it. Re-activating Mawer alone would restore it immediately.

### Funds

| Manager | Fund (as registered) | Mandate | Document |
|---|---|---|---|
| Mawer | Mawer International Equity Fund | international | two URLs on file (manager retired) |
| Kopernik | Kopernik Global All-Cap | global | **none — 미수집** |
| Kopernik | Kopernik International | international | **none — 미수집** |
| DRZ | DRZ Emerging Markets Value | emerging | **none — 미수집** |

DRZ's US Micro/Small/SMID/Large-Cap Value strategies are deliberately absent: a US-only
mandate cannot hold a Korean security.

---

## Open items

**1. Does Kopernik file N-PORT?** The highest-value question — a yes removes the $116M
ceiling for that manager and makes its fact sheets not worth parsing at all.

- Fastest check: does the fund page carry a **ticker and a prospectus**? A US-registered
  open-end fund must have both.
- Definitive: EDGAR **full-text** search, `q="Kopernik" forms=NPORT-P`.
- **Do not search the adviser CIK `0001599814`** — a fund files under its own registrant,
  and boutique advisers often run their funds as series of a third-party umbrella trust
  whose name contains nothing recognisable. A company-name search finds nothing in that
  case, and the absence proves nothing.

**2. Document URLs** for the three registered funds. One line each once seen.

**3. Proxy voting collector.** Table, classification and tab are built and tested; missing
a collector, gated on a seen URL and an observed layout. Under NI 81-106 the record is
posted on the fund's own website, not SEDAR+ — so it sits beside the fact sheets already
being hunted. Collect both in one pass.

**4. One free question to a data vendor.** "For Canadian mutual funds, do you carry the
complete portfolio, or only the MRFP top 25?" Complete → the ceiling becomes a purchasing
decision. Top 25 → the commercial route buys convenience only.

**5. CRDs** for DRZ and Kopernik (Form ADV / official RAUM), DRZ's website, Kopernik's
team-page path.

---

## Where things live

```
config.py                          MANAGERS / FUNDS registries — the source of truth
db/migrations/004_fund_holdings.sql   funds + fund_holdings
db/migrations/005_proxy_votes.sql     proxy_votes
db/migrations/006_fund_snapshots.sql  fund NAV per period
collectors/factsheet.py            fetch fund documents (both URL shapes, 4 cadences)
parsers/parse_factsheet.py         Mawer layout + the anti-silence rules
parsers/securities.py              security_key, is_korean
dashboard/queries.py               kr_evidence / kr_fund_coverage / kr_weight_series
dashboard/templates/korea.html     the tab
tests/fixtures/mawer_international_equity_series_f.txt   the calibration document
```

**Local development needs a database.** There is no Postgres in a fresh sandbox and the
DB-backed tests silently `skip` without one — roughly half the suite. `initdb` under
`/var/lib/postgresql` (not a scratchpad; the `postgres` user cannot traverse it) and point
`DATABASE_URL` at the socket.
