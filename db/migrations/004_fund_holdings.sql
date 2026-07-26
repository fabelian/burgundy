-- 004_fund_holdings.sql — holdings disclosed by the managers' own fund documents.
--
-- Why a second holdings table rather than more rows in ``holdings``:
-- ``holdings`` is a 13F information table (CUSIP, share count, USD thousands,
-- keyed by accession number). A fund fact sheet has none of those — no CUSIP,
-- frequently no share count, usually only a percentage weight, and no filing
-- identifier at all. Forcing one into the other would mean inventing a CUSIP
-- and an accession number, and the uniqueness rules would then be built on
-- invented values.
--
-- This is the only source that reaches a Korean large cap for these managers
-- (see docs/korea-holdings.md): the 5% rule can only ever surface small caps,
-- and none of the five file N-PORT.

-- ---------------------------------------------------------------------------
-- Which funds are worth reading
-- ---------------------------------------------------------------------------
-- Korean positions can only sit in International / Global / Emerging Markets
-- mandates, so the registry records the mandate and the collector skips the
-- Canadian and US-only funds rather than downloading them to discover they
-- hold nothing Korean.
CREATE TABLE IF NOT EXISTS funds (
  id             BIGSERIAL PRIMARY KEY,
  manager_id     BIGINT NOT NULL REFERENCES managers(id),
  slug           TEXT NOT NULL,          -- url-safe key, unique per manager
  name           TEXT NOT NULL,
  mandate        TEXT NOT NULL,          -- international | global | emerging | other
  series         TEXT,                   -- 'Series A' etc; series differ in fees, not holdings
  currency       TEXT NOT NULL DEFAULT 'CAD',
  -- Managers publish fact sheets in one of two shapes, and a fund may offer
  -- both, so both are stored:
  --
  --   doc_url_template  the period is *in* the path ({yyyy}/{yy}/{q}/{mm}).
  --                     Expanding it reaches past quarters, which is the only
  --                     way to build a trend rather than a single point.
  --   doc_url           one address whose contents are replaced each period.
  --                     Only ever the latest, and it must be re-read every
  --                     time — see the collector's dedup note.
  doc_url_template TEXT,
  doc_url        TEXT,
  cadence        TEXT NOT NULL DEFAULT 'quarterly',  -- quarterly | monthly
  is_active      BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order     INT NOT NULL DEFAULT 100,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (manager_id, slug)
);

-- ---------------------------------------------------------------------------
-- The positions themselves
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fund_holdings (
  id             BIGSERIAL PRIMARY KEY,
  manager_id     BIGINT NOT NULL REFERENCES managers(id),
  fund_id        BIGINT NOT NULL REFERENCES funds(id),
  as_of_date     DATE NOT NULL,          -- the position date the document states
  published_at   DATE,                   -- when the document appeared, when known
  -- Fact sheets identify a security by name only: no CUSIP, rarely an ISIN.
  -- security_key is the normalised name (see parsers.securities.security_key)
  -- and is what makes an insert idempotent across re-fetches of the same
  -- document, where the printed name may differ by punctuation or casing.
  security_key   TEXT NOT NULL,
  security_name  TEXT NOT NULL,          -- as printed
  ticker         TEXT,
  isin           TEXT,
  country        TEXT,                   -- exactly as the document printed it
  -- Classified once, on write, by parsers.securities.is_korean — never by a
  -- LIKE over names at read time. The Korea tab is the whole point of this
  -- table and it must not depend on each parser remembering to tag a row:
  -- FundHoldingRow fills this in for every row that reaches the database.
  is_korean      BOOLEAN NOT NULL DEFAULT FALSE,
  weight         NUMERIC(8,5),           -- percent of the fund
  market_value   NUMERIC(20,2),          -- when disclosed; most sheets omit it
  currency       TEXT,
  position_rank  INT,                    -- 1 = largest, as listed
  -- Most fact sheets print only the top ten positions. Recording the scope is
  -- what keeps the dashboard honest: with 'top_n', a manager not shown holding
  -- Samsung has *not* been shown to be absent from it — the position may simply
  -- sit outside the printed list. Reading absence as evidence would be exactly
  -- the wrong conclusion for a sales approach.
  disclosure_scope TEXT NOT NULL DEFAULT 'top_n',  -- top_n | full
  positions_listed INT,                  -- how many rows the document printed
  raw_id         BIGINT REFERENCES raw_documents(id),
  UNIQUE (fund_id, as_of_date, security_key)
);

CREATE INDEX IF NOT EXISTS fund_holdings_manager_asof_idx
  ON fund_holdings (manager_id, as_of_date DESC);
CREATE INDEX IF NOT EXISTS fund_holdings_fund_asof_idx
  ON fund_holdings (fund_id, as_of_date DESC);
-- The Korea tab reads every manager's Korean rows at once, so the index covers
-- the flag rather than the manager.
CREATE INDEX IF NOT EXISTS fund_holdings_korean_idx
  ON fund_holdings (as_of_date DESC) WHERE is_korean;
CREATE INDEX IF NOT EXISTS funds_manager_idx ON funds (manager_id, sort_order);
