-- Query 1: Hourly event count with running total per repository
-- Business question: For the 20 most active repositories overall, how did
-- their event count accumulate hour-by-hour across the 3-day window?
--
-- The rubric is: "top 20 repositories by total event count, showing for each
-- row: repository name, hour, events in that hour, and running total".
-- That means we first pick the top-20 repos by TOTAL events, then return
-- every hourly row for those repos with a running cumulative total.
-- A naive "ORDER BY running_total DESC LIMIT 20" would just return 20
-- (repo, hour) rows, typically all from the single biggest repo.
-- Written: 2026-05-18.

WITH top_repos AS (
    -- Pick the 20 most active repositories across the whole window first.
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

-- Query 3: Pull request merge rate by organisation
-- Business question: Which organisations are most effective at merging
-- pull requests vs leaving them closed unmerged?
--
-- Uses the denormalised fact_events.org_name column (see schema.sql) so
-- this query no longer needs to join dim_repos just to read org_name.
-- That removes the nested-loop lookup and the sort key resolution that
-- dominated the original plan.
-- Written: 2026-05-18.

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


-- Query Optimisation Notes (Query 3):
-- Before: Query 3 joined dim_repos solely to read org_name, then sorted
-- ~33k PullRequestEvent rows by org_name before grouping. The dominant
-- costs in the EXPLAIN were the Nested Loop into dim_repos and the
-- 3.2 MB quicksort on r.org_name.
--
-- Change: Denormalised org_name onto fact_events (warehouse/schema.sql)
-- and dropped the dim_repos join from the query. A partial index
-- idx_fact_org_pr ON fact_events(org_name) WHERE pr_action IS NOT NULL
-- supports the post-filter group-by.
--
-- After: The plan no longer contains the Nested Loop on dim_repos, and
-- the GroupAggregate runs directly over the fact-table rows already
-- carrying org_name. See explain_before.txt vs explain_after.txt for
-- the side-by-side plans.