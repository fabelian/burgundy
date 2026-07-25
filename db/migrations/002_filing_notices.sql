-- 002_filing_notices.sql
-- Records 13F-NT (Notice) filings: quarters where the manager reports NO
-- holdings itself because another manager (e.g. an acquirer) reports them.
-- Lets the dashboard explain why standalone holdings stop at a given quarter.

CREATE TABLE IF NOT EXISTS filing_notices (
  id             BIGSERIAL PRIMARY KEY,
  as_of_date     DATE NOT NULL,          -- quarter end
  filed_at       DATE NOT NULL,
  accession_no   TEXT NOT NULL,
  form           TEXT NOT NULL,          -- '13F-NT' | '13F-NT/A'
  report_type    TEXT,                   -- cover page report type text
  other_managers TEXT,                   -- managers reporting on this filer's behalf
  raw_id         BIGINT REFERENCES raw_documents(id),
  UNIQUE (accession_no)
);

CREATE INDEX IF NOT EXISTS filing_notices_asof_idx ON filing_notices (as_of_date DESC);
