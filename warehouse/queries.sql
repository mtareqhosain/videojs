-- Query 1: Hourly event count with running total per repository.
-- Business question: for the 20 most active repositories overall, how
-- did their event count accumulate hour-by-hour across the window?

WITH top_repos AS (
    SELECT repo_id
    FROM fact_events
    GROUP BY repo_id
    ORDER BY COUNT(*) DESC
    LIMIT 20
)
SELECT
    dr.repo_name,
    dt.hour_bucket,
    COUNT(*) AS events_this_hour,
    SUM(COUNT(*)) OVER (
        PARTITION BY dr.repo_id
        ORDER BY dt.hour_bucket
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM fact_events fe
JOIN top_repos tr ON tr.repo_id = fe.repo_id
JOIN dim_repos dr ON fe.repo_id = dr.repo_id
JOIN dim_time  dt ON fe.time_id = dt.time_id
GROUP BY dr.repo_id, dr.repo_name, dt.hour_bucket
ORDER BY dr.repo_name, dt.hour_bucket;


-- Query 2: User contribution profile across event types
-- Business question: What percentage of users are specialists (single event type)
-- vs generalists vs power users (5+ distinct event types)?

SELECT
    tier,
    COUNT(*) AS user_count
FROM (
    SELECT
        u.login,
        COUNT(DISTINCT et.event_type_name) AS distinct_types,
        CASE
            WHEN COUNT(DISTINCT et.event_type_name) = 1 THEN 'single-type'
            WHEN COUNT(DISTINCT et.event_type_name) BETWEEN 2 AND 4 THEN 'multi-type'
            ELSE 'power user'
        END AS tier
    FROM fact_events f
    JOIN dim_users u USING (user_id)
    JOIN dim_event_types et USING (event_type_id)
    GROUP BY u.login
) tiers
GROUP BY tier
ORDER BY user_count DESC;

-- Query 3: Pull request merge rate by organisation.
-- Business question: which organisations are most effective at merging
-- pull requests vs leaving them closed unmerged?
-- Reads org_name directly from fact_events (denormalised) — see DESIGN.md.

SELECT
    f.org_name,
    ROUND(
        COUNT(*) FILTER (WHERE f.pr_action = 'closed' AND f.pr_merged = TRUE)::NUMERIC
        / NULLIF(COUNT(*) FILTER (WHERE f.pr_action = 'closed'), 0) * 100,
        2
    ) AS merge_rate_pct,
    COUNT(*) FILTER (WHERE f.pr_action = 'closed') AS total_closed
FROM fact_events f
JOIN dim_event_types et USING (event_type_id)
WHERE et.event_type_name = 'PullRequestEvent'
GROUP BY f.org_name
HAVING COUNT(*) FILTER (WHERE f.pr_action = 'closed') > 10
ORDER BY merge_rate_pct DESC
LIMIT 20;


-- Query 3 optimisation: full write-up in warehouse/DESIGN.md.
-- See explain_before.txt and explain_after.txt for the EXPLAIN plans.