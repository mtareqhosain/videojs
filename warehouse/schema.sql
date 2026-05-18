-- dimension time
CREATE TABLE IF NOT EXISTS dim_time (
    time_id SERIAL PRIMARY KEY,
    hour_bucket TIMESTAMPTZ NOT NULL UNIQUE,
    day DATE NOT NULL,
    month INT NOT NULL,
    year INT NOT NULL
);

-- dimension user
CREATE TABLE IF NOT EXISTS dim_users (
    user_id SERIAL PRIMARY KEY,
    login TEXT NOT NULL UNIQUE
);

-- dimension repository
CREATE TABLE IF NOT EXISTS dim_repos (
    repo_id SERIAL PRIMARY KEY,
    repo_name TEXT NOT NULL UNIQUE,
    org_name TEXT
);

-- dimension event types
CREATE TABLE IF NOT EXISTS dim_event_types (
    event_type_id SERIAL PRIMARY KEY,
    event_type_name TEXT NOT NULL UNIQUE
);


-- fact table, one row per event.
-- org_name is a degenerate-style denormalisation: it's an attribute of the
-- repository, but pre-joining it onto the fact table removes the join+sort
-- in Query 3 (PR merge rate by org). This is the optimisation walked
-- through in DESIGN.md and explain_before.txt / explain_after.txt.
-- Written: 2026-05-18.
CREATE TABLE IF NOT EXISTS fact_events (
    event_id TEXT PRIMARY KEY,
    event_type_id INT REFERENCES dim_event_types(event_type_id),
    user_id INT REFERENCES dim_users(user_id),
    repo_id INT REFERENCES dim_repos(repo_id),
    time_id INT REFERENCES dim_time(time_id),
    org_name TEXT,
    pr_action TEXT,
    pr_merged BOOLEAN
);

-- Indexes (each justified in warehouse/DESIGN.md).
CREATE INDEX IF NOT EXISTS idx_fact_repo       ON fact_events(repo_id);
CREATE INDEX IF NOT EXISTS idx_fact_user       ON fact_events(user_id);
CREATE INDEX IF NOT EXISTS idx_fact_event_type ON fact_events(event_type_id);
CREATE INDEX IF NOT EXISTS idx_fact_pr         ON fact_events(pr_action, pr_merged) WHERE pr_action IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dim_time_hour   ON dim_time(hour_bucket);
-- Partial index for the Query 3 hot path: PR-event rows grouped by org_name.
-- Covers the post-denormalisation lookup of "closed PRs by org".
CREATE INDEX IF NOT EXISTS idx_fact_org_pr     ON fact_events(org_name)
    WHERE pr_action IS NOT NULL;