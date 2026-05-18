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
JOIN dim_repos dr ON fe.repo_id = dr.repo_id
JOIN dim_time dt ON fe.time_id = dt.time_id
GROUP BY dr.repo_id, dr.repo_name, dt.hour_bucket
ORDER BY running_total DESC
LIMIT 20;


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

-- Query 3: Pull request merge rate by organisation
-- Business question: Which organisations are most effective at merging 
-- pull requests vs leaving them closed unmerged?

SELECT
    r.org_name,
    ROUND(
        COUNT(*) FILTER (WHERE f.pr_action = 'closed' AND f.pr_merged = TRUE)::NUMERIC
        / NULLIF(COUNT(*) FILTER (WHERE f.pr_action = 'closed'), 0) * 100,
        2
    ) AS merge_rate_pct,
    COUNT(*) FILTER (WHERE f.pr_action = 'closed') AS total_closed
FROM fact_events f
JOIN dim_repos r USING (repo_id)
JOIN dim_event_types et USING (event_type_id)
WHERE et.event_type_name = 'PullRequestEvent'
GROUP BY r.org_name
HAVING COUNT(*) FILTER (WHERE f.pr_action = 'closed') > 10
ORDER BY merge_rate_pct DESC
LIMIT 20;