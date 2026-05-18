# Warehouse Design Document

## Grain Decision
One row in fact_events represents one GitHub event. This is the finest possible grain, giving analysts full flexibility to aggregate at any level — by hour, day, user, repo, or event type — without losing detail.

## Dimension Table Choices
Four dimensions capture the key analytical axes: dim_users (who performed the action), dim_repos (which repository and organisation), dim_time (when, bucketed by hour), and dim_event_types (what type of event). These cover the core questions analysts ask about GitHub activity patterns.

## Indexing Rationale
- idx_fact_repo: Query 1 groups by repo_id — index prevents full scan
- idx_fact_user: Query 2 groups by user_id — index speeds aggregation
- idx_fact_event_type: Query 3 filters by event_type_id — most selective filter
- idx_fact_pr: Partial index on pr_action/pr_merged for non-null rows only — reduces index size
- idx_dim_time_hour: Window function in Query 1 orders by hour_bucket — index supports sort
- idx_dim_repos_org: Query 3 groups by org_name — added during optimisation, gave 25% speedup

## Transformation Idempotency
We use TRUNCATE + INSERT rather than UPSERT. Since raw_events is always the source of truth, a full rebuild of the warehouse on each run is safe and simple. UPSERT would add complexity without benefit at this volume. Dimensions are truncated before the fact table to respect foreign key constraints.

## Query Optimisation
Query 3 originally took 253ms due to a sort on org_name over 33,574 PullRequestEvent rows. Adding idx_fact_repo_org on dim_repos(org_name, repo_id) reduced this to 188ms — a 25% improvement by allowing more efficient org_name resolution during the nested loop join.

## One Thing I Would Add in Production
Incremental fact table updates using dbt instead of full TRUNCATE + INSERT. At larger volumes, rebuilding the entire fact table on every transform run becomes expensive. dbt's incremental models would only process new raw_events since the last run, using the created_at watermark.