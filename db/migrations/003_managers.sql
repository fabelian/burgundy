-- 003_managers.sql — track several managers in one database.
--
-- Every snapshot table gains a manager_id, and every uniqueness rule is
-- re-scoped to it. aum_history is the one that would corrupt data if missed:
-- UNIQUE (as_of_date, source) is global, so a second manager's 13f_total for a
-- quarter would silently collide with the first one's.

CREATE TABLE IF NOT EXISTS managers (
  id                BIGSERIAL PRIMARY KEY,
  slug              TEXT NOT NULL UNIQUE,   -- url-safe key used by the dashboard
  name              TEXT NOT NULL,
  legal_name        TEXT,                   -- name as filed with the SEC, when it differs
  cik               TEXT,                   -- resolved from EDGAR on first run
  crd               TEXT,                   -- Form ADV firm id; NULL = skip Form ADV
  website_aum_url   TEXT,
  website_team_url  TEXT,
  dart_terms        TEXT[] NOT NULL DEFAULT '{}',  -- empty = skip the Korean collector
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order        INT NOT NULL DEFAULT 100,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (cik)
);

-- The manager this database was built for. Everything already collected is his.
INSERT INTO managers (slug, name, legal_name, cik, crd,
                      website_aum_url, website_team_url, dart_terms, sort_order)
VALUES ('burgundy', 'Burgundy Asset Management',
        'BURGUNDY ASSET MANAGEMENT LTD.', '0001315868', '114317',
        'https://www.burgundyasset.com/',
        'https://www.burgundyasset.com/about-us/our-team/',
        ARRAY['버건디', 'Burgundy'], 0)
ON CONFLICT (slug) DO NOTHING;

ALTER TABLE raw_documents  ADD COLUMN IF NOT EXISTS manager_id BIGINT REFERENCES managers(id);
ALTER TABLE holdings       ADD COLUMN IF NOT EXISTS manager_id BIGINT REFERENCES managers(id);
ALTER TABLE kr_holdings    ADD COLUMN IF NOT EXISTS manager_id BIGINT REFERENCES managers(id);
ALTER TABLE aum_history    ADD COLUMN IF NOT EXISTS manager_id BIGINT REFERENCES managers(id);
ALTER TABLE personnel      ADD COLUMN IF NOT EXISTS manager_id BIGINT REFERENCES managers(id);
ALTER TABLE changes        ADD COLUMN IF NOT EXISTS manager_id BIGINT REFERENCES managers(id);
ALTER TABLE collector_runs ADD COLUMN IF NOT EXISTS manager_id BIGINT REFERENCES managers(id);
ALTER TABLE filing_notices ADD COLUMN IF NOT EXISTS manager_id BIGINT REFERENCES managers(id);

-- Backfill: every pre-existing row belongs to Burgundy.
UPDATE raw_documents  SET manager_id = (SELECT id FROM managers WHERE slug='burgundy') WHERE manager_id IS NULL;
UPDATE holdings       SET manager_id = (SELECT id FROM managers WHERE slug='burgundy') WHERE manager_id IS NULL;
UPDATE kr_holdings    SET manager_id = (SELECT id FROM managers WHERE slug='burgundy') WHERE manager_id IS NULL;
UPDATE aum_history    SET manager_id = (SELECT id FROM managers WHERE slug='burgundy') WHERE manager_id IS NULL;
UPDATE personnel      SET manager_id = (SELECT id FROM managers WHERE slug='burgundy') WHERE manager_id IS NULL;
UPDATE changes        SET manager_id = (SELECT id FROM managers WHERE slug='burgundy') WHERE manager_id IS NULL;
UPDATE collector_runs SET manager_id = (SELECT id FROM managers WHERE slug='burgundy') WHERE manager_id IS NULL;
UPDATE filing_notices SET manager_id = (SELECT id FROM managers WHERE slug='burgundy') WHERE manager_id IS NULL;

ALTER TABLE raw_documents  ALTER COLUMN manager_id SET NOT NULL;
ALTER TABLE holdings       ALTER COLUMN manager_id SET NOT NULL;
ALTER TABLE kr_holdings    ALTER COLUMN manager_id SET NOT NULL;
ALTER TABLE aum_history    ALTER COLUMN manager_id SET NOT NULL;
ALTER TABLE personnel      ALTER COLUMN manager_id SET NOT NULL;
ALTER TABLE changes        ALTER COLUMN manager_id SET NOT NULL;
ALTER TABLE collector_runs ALTER COLUMN manager_id SET NOT NULL;
ALTER TABLE filing_notices ALTER COLUMN manager_id SET NOT NULL;

-- Re-scope every uniqueness rule to the manager.
ALTER TABLE raw_documents  DROP CONSTRAINT IF EXISTS raw_documents_source_content_hash_key;
ALTER TABLE raw_documents  ADD  CONSTRAINT raw_documents_manager_source_hash_key
      UNIQUE (manager_id, source, content_hash);

ALTER TABLE holdings       DROP CONSTRAINT IF EXISTS holdings_accession_no_cusip_key;
ALTER TABLE holdings       ADD  CONSTRAINT holdings_manager_accession_cusip_key
      UNIQUE (manager_id, accession_no, cusip);

ALTER TABLE kr_holdings    DROP CONSTRAINT IF EXISTS kr_holdings_rcept_no_corp_code_key;
ALTER TABLE kr_holdings    ADD  CONSTRAINT kr_holdings_manager_rcept_corp_key
      UNIQUE (manager_id, rcept_no, corp_code);

ALTER TABLE aum_history    DROP CONSTRAINT IF EXISTS aum_history_as_of_date_source_key;
ALTER TABLE aum_history    ADD  CONSTRAINT aum_history_manager_asof_source_key
      UNIQUE (manager_id, as_of_date, source);

ALTER TABLE filing_notices DROP CONSTRAINT IF EXISTS filing_notices_accession_no_key;
ALTER TABLE filing_notices ADD  CONSTRAINT filing_notices_manager_accession_key
      UNIQUE (manager_id, accession_no);

DROP INDEX IF EXISTS changes_dedup_idx;
CREATE UNIQUE INDEX IF NOT EXISTS changes_dedup_idx
  ON changes (manager_id, entity_type, entity_key, as_of_date, change_type);

CREATE INDEX IF NOT EXISTS holdings_manager_asof_idx   ON holdings (manager_id, as_of_date);
CREATE INDEX IF NOT EXISTS aum_history_manager_idx     ON aum_history (manager_id, source, as_of_date);
CREATE INDEX IF NOT EXISTS changes_manager_idx         ON changes (manager_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS collector_runs_manager_idx  ON collector_runs (manager_id, started_at DESC);
CREATE INDEX IF NOT EXISTS personnel_manager_idx       ON personnel (manager_id, valid_to);
