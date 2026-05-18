-- Truncate in correct order (fact first, then dims)
TRUNCATE TABLE fact_events CASCADE;
TRUNCATE TABLE dim_time CASCADE;
TRUNCATE TABLE dim_users CASCADE;
TRUNCATE TABLE dim_repos CASCADE;
TRUNCATE TABLE dim_event_types CASCADE;

-- Populate dim_time
INSERT INTO dim_time (hour_bucket, day, month, year)
SELECT DISTINCT
    DATE_TRUNC('hour', created_at) AS hour_bucket,
    DATE_TRUNC('day', created_at)::DATE AS day,
    EXTRACT(MONTH FROM created_at)::INT AS month,
    EXTRACT(YEAR FROM created_at)::INT AS year
FROM raw_events
WHERE created_at IS NOT NULL;

-- Populate dim_users
INSERT INTO dim_users (login)
SELECT DISTINCT actor_login
FROM raw_events
WHERE actor_login IS NOT NULL;

-- Populate dim_repos
INSERT INTO dim_repos (repo_name, org_name)
SELECT DISTINCT
    repo_name,
    SPLIT_PART(repo_name, '/', 1) AS org_name
FROM raw_events
WHERE repo_name IS NOT NULL;

-- Populate dim_event_types
INSERT INTO dim_event_types (event_type_name)
SELECT DISTINCT event_type
FROM raw_events
WHERE event_type IS NOT NULL;

-- Populate fact_events.
-- org_name is denormalised onto the fact table so Query 3 (PR merge rate
-- by org) can group/filter without joining dim_repos. See DESIGN.md and
-- explain_after.txt for the resulting plan change.
-- Written: 2026-05-18.
INSERT INTO fact_events (
    event_id, event_type_id, user_id, repo_id, time_id, org_name, pr_action, pr_merged
)
SELECT
    e.id,
    et.event_type_id,
    u.user_id,
    r.repo_id,
    t.time_id,
    r.org_name,
    e.payload->>'action',
    (e.payload->'pull_request'->>'merged')::BOOLEAN
FROM raw_events e
JOIN dim_event_types et ON et.event_type_name = e.event_type
JOIN dim_users u ON u.login = e.actor_login
JOIN dim_repos r ON r.repo_name = e.repo_name
JOIN dim_time t ON t.hour_bucket = DATE_TRUNC('hour', e.created_at)
WHERE e.id IS NOT NULL;