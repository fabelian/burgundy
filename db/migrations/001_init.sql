-- 001_init.sql — Burgundy tracker schema.
-- 3-layer append-only design: raw -> snapshot -> changes.

-- Layer 1: immutable originals
CREATE TABLE IF NOT EXISTS raw_documents (
  id            BIGSERIAL PRIMARY KEY,
  source        TEXT NOT NULL,          -- 'edgar_13f' | 'dart_5pct' | 'form_adv' | 'website_team' | 'website_aum'
  external_id   TEXT,                   -- accession_no / rcept_no / null
  url           TEXT NOT NULL,
  content_hash  TEXT NOT NULL,          -- sha256
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload       TEXT NOT NULL,          -- raw content (XML/JSON/HTML)
  UNIQUE (source, content_hash)
);

-- Layer 2: snapshots (append-only)
CREATE TABLE IF NOT EXISTS holdings (   -- 13F US holdings
  id            BIGSERIAL PRIMARY KEY,
  as_of_date    DATE NOT NULL,          -- quarter end
  filed_at      DATE NOT NULL,
  accession_no  TEXT NOT NULL,
  is_amendment  BOOLEAN NOT NULL DEFAULT FALSE,
  cusip         TEXT NOT NULL,
  ticker        TEXT,
  name          TEXT NOT NULL,
  shares        BIGINT NOT NULL,
  value_kusd    BIGINT NOT NULL,        -- 13F unit: USD thousands
  weight        NUMERIC(8,5),           -- weight within the filing (computed after parse)
  raw_id        BIGINT REFERENCES raw_documents(id),
  UNIQUE (accession_no, cusip)
);

CREATE TABLE IF NOT EXISTS kr_holdings ( -- DART Korean stakes
  id            BIGSERIAL PRIMARY KEY,
  as_of_date    DATE NOT NULL,          -- report basis date
  filed_at      DATE NOT NULL,
  rcept_no      TEXT NOT NULL,
  corp_code     TEXT NOT NULL,
  corp_name     TEXT NOT NULL,
  ticker        TEXT,
  shares        BIGINT,
  ownership_pct NUMERIC(7,4),
  report_type   TEXT,                   -- 신규/변동/처분 등
  raw_id        BIGINT REFERENCES raw_documents(id),
  UNIQUE (rcept_no, corp_code)
);

CREATE TABLE IF NOT EXISTS aum_history (
  id            BIGSERIAL PRIMARY KEY,
  as_of_date    DATE NOT NULL,
  aum           NUMERIC(20,2) NOT NULL,
  currency      TEXT NOT NULL DEFAULT 'CAD',
  source        TEXT NOT NULL,          -- 'form_adv' | '13f_total' | 'website'
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  raw_id        BIGINT REFERENCES raw_documents(id),
  UNIQUE (as_of_date, source)
);

-- SCD Type 2
CREATE TABLE IF NOT EXISTS personnel (
  id            BIGSERIAL PRIMARY KEY,
  person_name   TEXT NOT NULL,
  title         TEXT NOT NULL,
  source        TEXT NOT NULL,
  valid_from    DATE NOT NULL,
  valid_to      DATE,                   -- NULL = currently valid
  raw_id        BIGINT REFERENCES raw_documents(id)
);

-- Layer 3: diff events
CREATE TABLE IF NOT EXISTS changes (
  id            BIGSERIAL PRIMARY KEY,
  detected_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  entity_type   TEXT NOT NULL,          -- 'us_holding' | 'kr_holding' | 'aum' | 'personnel'
  change_type   TEXT NOT NULL,          -- NEW_POSITION | EXITED | INCREASED | DECREASED |
                                        -- STAKE_CHANGED | PERSON_JOINED | PERSON_LEFT | TITLE_CHANGED | AUM_UPDATED
  entity_key    TEXT NOT NULL,          -- cusip / ticker / person_name etc.
  before        JSONB,
  after         JSONB,
  as_of_date    DATE
);

-- Prevent duplicate diff events on re-run.
CREATE UNIQUE INDEX IF NOT EXISTS changes_dedup_idx
  ON changes (entity_type, entity_key, as_of_date, change_type);

CREATE TABLE IF NOT EXISTS collector_runs ( -- operational visibility
  id            BIGSERIAL PRIMARY KEY,
  collector     TEXT NOT NULL,
  started_at    TIMESTAMPTZ NOT NULL,
  finished_at   TIMESTAMPTZ,
  status        TEXT NOT NULL,          -- ok | error | skipped
  new_raw       INT DEFAULT 0,
  new_rows      INT DEFAULT 0,
  error_msg     TEXT
);

CREATE INDEX IF NOT EXISTS holdings_asof_idx ON holdings (as_of_date);
CREATE INDEX IF NOT EXISTS kr_holdings_corp_idx ON kr_holdings (corp_code, as_of_date);
CREATE INDEX IF NOT EXISTS changes_detected_idx ON changes (detected_at DESC);
CREATE INDEX IF NOT EXISTS collector_runs_idx ON collector_runs (collector, started_at DESC);
