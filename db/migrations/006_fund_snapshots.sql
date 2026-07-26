-- 006_fund_snapshots.sql — what a fund document says about the fund itself.
--
-- A weight alone is not an answer. "3%" only means something against the fund
-- it is 3% of, and the fact sheet states that number — it was being parsed and
-- thrown away. With the NAV kept, 3.0% of Mawer International Equity becomes
-- roughly C$218M, which is the figure a sales conversation actually turns on.
--
-- Separate from fund_holdings because the grain is different: one NAV per fund
-- per period, not one per position. It also keeps ``total_holdings`` — the
-- whole portfolio count, against which ``positions_listed`` is the printed
-- extract — which until now was read to decide disclosure_scope and discarded.
--
-- Per period rather than on ``funds``: NAV moves every quarter, and a weight
-- from an old document has to be read against that period's NAV, not today's.

CREATE TABLE IF NOT EXISTS fund_snapshots (
  id             BIGSERIAL PRIMARY KEY,
  manager_id     BIGINT NOT NULL REFERENCES managers(id),
  fund_id        BIGINT NOT NULL REFERENCES funds(id),
  as_of_date     DATE NOT NULL,
  -- Net assets of the *fund*, in absolute units (not millions) to match
  -- aum_history. Fact sheets print several similar figures — the fund, one
  -- series of it, and the per-unit value — and picking the wrong one is a
  -- silent order-of-magnitude error, so the parser anchors strictly.
  nav            NUMERIC(20,2),
  nav_currency   TEXT,
  total_holdings INT,          -- whole portfolio; positions_listed is the extract
  raw_id         BIGINT REFERENCES raw_documents(id),
  UNIQUE (fund_id, as_of_date)
);

CREATE INDEX IF NOT EXISTS fund_snapshots_manager_idx
  ON fund_snapshots (manager_id, as_of_date DESC);
