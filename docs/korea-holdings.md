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

## Next step (not yet built)

1. `fund_holdings` table — manager, fund, as-of date, security, weight, country.
2. A fact-sheet collector per manager: enumerate International/Global/EM funds, fetch the
   latest quarterly or monthly document, parse the holdings table, flag Korean names.
3. Replace the Korea tab with per-manager Korean holdings across the five.

**Blocked on seeing a real fact sheet.** The development sandbox has no outbound access
to the managers' sites (`403` from both WebFetch and curl — the network policy is fixed
at container start), so a parser written here would be written blind against a format
never observed, which is how the DART sweep went wrong. Production has the access it
needs; only development is blocked. Start by obtaining one Mawer International Equity
fact sheet, then build the parser against it.

## Operational notes

- **The collector service picks its job from a config file.** `railway.collector.json` is
  the daily cron; `railway.backfill.json`, `railway.backfill_kr.json`, `railway.heal.json`
  and `railway.reparse.json` are one-shot jobs. Whichever is selected runs on *every*
  deploy.
- **Merging to main redeploys the collector**, which restarts whatever that config runs.
  A long backfill was killed twice this way. Switch the config file back before merging.
- The Korean sweep now **refuses to start without an explicit `--since` /
  `KR_BACKFILL_SINCE`**, so it can no longer restart itself on an unrelated deploy.
