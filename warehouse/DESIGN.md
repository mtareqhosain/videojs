# Warehouse Design Notes

## Grain

One row in `fact_events` is one GitHub event. That's it — no rollups, no pre-aggregation. I went with the lowest grain on purpose: every analytical question in this assessment (hourly counts, per-user breakdowns, PR merge rate) is either at event grain or trivially aggregated from it, and once you pre-aggregate you can't go back without re-reading raw_events.

The price is row count (≈546k for the 3 sample files, would be ≈40M for the full 3 days). For the volumes we're dealing with that's still comfortable on a single Postgres instance.

## Dimensions

Four dims, picked because they're the axes every query in `queries.sql` actually slices by:

- `dim_users` — the actor login. SCD type 1; if a user renames, the new login becomes a new row. Acceptable for analytics, not for audit.
- `dim_repos` — repo full name + parsed `org_name`. The `org_name` parsing (split on `/`) is the same logic we use in `transform.sql`.
- `dim_time` — bucketed to the hour. The brief only asks for hourly analysis, so anything finer is wasted rows.
- `dim_event_types` — there are 20+ event types in GH Archive. Keeping them in their own dim means the fact table stores an int instead of a string, and Q2 / Q3 can filter by name without scanning text.

There's no `dim_org` on purpose — `org_name` lives on `dim_repos`, and after the Query 3 optimisation it's also denormalised onto the fact table. Adding a separate org dim would mean two more joins on every PR query for no extra information.

## Indexes (and why each one is there)

These are the indexes in `schema.sql`. The rule I followed: only add an index that has a named query attached to it.

- `idx_fact_repo` on `fact_events(repo_id)` — Query 1 groups by repo, and the CTE that picks the top-20 repos does a COUNT(*) GROUP BY repo_id over the whole fact table.
- `idx_fact_user` on `fact_events(user_id)` — Query 2 aggregates per user.
- `idx_fact_event_type` on `fact_events(event_type_id)` — Query 3 filters to `PullRequestEvent` (just one of ~15 event types in the sample), so this is the most selective predicate in that query.
- `idx_fact_pr` on `fact_events(pr_action, pr_merged) WHERE pr_action IS NOT NULL` — partial, because >80% of events have no PR action at all. Supports the FILTER aggregates in Query 3.
- `idx_dim_time_hour` on `dim_time(hour_bucket)` — Query 1's window function orders by hour; this also helps any date-range scan from the MCP `top_repos_by_event_count` tool.
- `idx_fact_org_pr` on `fact_events(org_name) WHERE pr_action IS NOT NULL` — added during the Query 3 optimisation pass, see below.

No indexes on the dim PKs beyond what Postgres creates for the PRIMARY KEY constraints. Dim tables are small enough that the planner can sequential-scan them when it wants to.

## Idempotency of the transform

`transform.sql` does TRUNCATE + INSERT, in foreign-key order (fact first, then dims, then re-populate dims, then re-populate fact). I considered UPSERT-into-fact but rejected it: `raw_events` is the source of truth and already idempotent (PK on `id`, ON CONFLICT DO NOTHING in `ingest.py`), so rebuilding the marts from scratch on every transform run is cheap relative to the alternative complexity. Roughly a second of TRUNCATE + INSERT for the 3-file sample.

This stops being the right answer somewhere around 100M fact rows. See "What I'd add in production" below.

## Query 3 — the optimisation pass

This is the slowest of the three queries; here's what I found and what I did about it.

**Original plan** (`explain_before.txt`, 115.98 ms, 139,144 buffer hits). The query joined `dim_repos` solely to read `org_name`, then grouped by `r.org_name`. The plan ended up doing a Nested Loop into `dim_repos`, one Index Scan on `dim_repos_pkey` per row — 33,574 lookups, 134,296 of the 139,144 buffer hits. After that, a 3.2 MB in-memory quicksort on `r.org_name` before GroupAggregate. The dim_repos lookup was clearly the fat part of the plan.

**Fix.** Three changes, all committed together — the denormalisation is the one doing the heavy lifting, the others just make the new path viable:

1. Denormalised `org_name` onto `fact_events` (see `schema.sql` and the final INSERT in `transform.sql`). Yes, this duplicates data — every PR event row now carries an `org_name` that could otherwise be looked up in the dim. The justification is that org is a stable, low-cardinality attribute and Query 3 is the most expensive analytical query.
2. Rewrote Query 3 to read `f.org_name` directly and dropped the `dim_repos` join (see `queries.sql`).
3. Added partial index `idx_fact_org_pr ON fact_events(org_name) WHERE pr_action IS NOT NULL` to support the post-filter GROUP BY path.

**Result** (`explain_after.txt`, 58.16 ms, 4,848 buffer hits). The plan no longer has any `dim_repos` node. Buffer hits dropped ~29× because the 33k dim_repos lookups are gone. Execution time roughly halved. The Sort + GroupAggregate is still in the plan because Postgres has to sort to group by `org_name`, but it's now sorting rows that already carry the column rather than joining-then-sorting.

The trade-off I'm explicitly making: `raw_events` is the source of truth, but if `dim_repos.org_name` and `fact_events.org_name` ever disagree it'll be because someone hand-edited a dim row. Since the transform rebuilds both from `raw_events`, this can't drift in normal operation.

## What I'd add in production

Incremental fact-table updates. TRUNCATE + INSERT is fine for the 3-file demo but will get embarrassing as raw_events grows. The natural move is dbt incremental models keyed on a high-watermark over `raw_events.created_at`
— only insert rows whose source event is newer than the last successful run. That also lets us partition `fact_events` by month and prune the transform to just the latest partition.

The other thing I'd want, but didn't add, is a `dq_*` set of test queries run after every transform (row counts vs raw_events, NULL ratios on critical FK columns, monotonic time_id). Without those, a bad transform just silently produces a smaller mart.
