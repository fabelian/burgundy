-- 005_proxy_votes.sql — holdings proved by a fund's own voting record.
--
-- Why this is a separate table from fund_holdings, and worth having at all:
-- a fact sheet prints the top 10–25 positions, so it cannot show a Korean
-- holding below roughly $116M (docs/korea-holdings.md, "The measurement
-- ceiling"). A proxy voting record under NI 81-106 has **no such ceiling** — it
-- lists every meeting the fund voted, so a 0.3% position appears exactly as a
-- 3% one does. It is the only free source that reaches under the floor.
--
-- What it does not carry is size. That is the point of keeping the two apart
-- rather than writing votes into fund_holdings with a NULL weight:
--
--   in both                    -> held, and sized
--   vote only, no fact sheet   -> held, but under the fact sheet's floor
--   fact sheet only            -> held; the vote record lags ~14 months
--   neither                    -> the closest to absence free data allows
--
-- Collapsing them would destroy exactly the distinction that makes the pair
-- worth having, and would put a meeting date in a column meaning "portfolio
-- as-of date".

CREATE TABLE IF NOT EXISTS proxy_votes (
  id             BIGSERIAL PRIMARY KEY,
  manager_id     BIGINT NOT NULL REFERENCES managers(id),
  -- NI 81-106 makes the voting record a *fund*-level obligation, so every row
  -- belongs to a fund. Keeping this NOT NULL also keeps the uniqueness rule
  -- honest: a nullable column in a unique key does not dedup, since NULLs do
  -- not compare equal.
  fund_id        BIGINT NOT NULL REFERENCES funds(id),
  period_ended   DATE NOT NULL,          -- the 12 months ending 30 June
  meeting_date   DATE NOT NULL,          -- what the holding is evidence *as of*
  -- Same normalised printed name as fund_holdings, which is what lets a vote
  -- for "Samsung Electronics Co., Ltd." meet a fact-sheet line reading
  -- "Samsung Electronics Co Ltd" without either being rewritten.
  security_key   TEXT NOT NULL,
  issuer_name    TEXT NOT NULL,          -- as printed
  ticker         TEXT,
  country        TEXT,
  is_korean      BOOLEAN NOT NULL DEFAULT FALSE,  -- classified on write, as in fund_holdings
  -- One row per meeting, not per ballot item. The evidence this table exists
  -- to record is "this fund held this issuer on this date"; twenty rows for
  -- twenty resolutions would say that twenty times and dedup would then hinge
  -- on matching free-text resolution titles across documents.
  ballots        INT,                    -- how many items were voted, when stated
  raw_id         BIGINT REFERENCES raw_documents(id),
  UNIQUE (fund_id, meeting_date, security_key)
);

CREATE INDEX IF NOT EXISTS proxy_votes_manager_idx
  ON proxy_votes (manager_id, meeting_date DESC);
-- The Korea tab reads every manager's Korean votes at once, as with holdings.
CREATE INDEX IF NOT EXISTS proxy_votes_korean_idx
  ON proxy_votes (meeting_date DESC) WHERE is_korean;
CREATE INDEX IF NOT EXISTS proxy_votes_security_idx
  ON proxy_votes (manager_id, security_key);
