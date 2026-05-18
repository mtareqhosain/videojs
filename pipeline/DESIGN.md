# Pipeline Design Notes

## Schema for the raw layer

GitHub Archive events are polymorphic: 20+ event types, each with a different `payload` shape. The three realistic options were:

1. One wide table with every possible column nullable.
2. One table per event type.
3. A hybrid: structured columns for the fields that exist on every event, plus a single `JSONB payload` for the type-specific stuff.

I went with option 3. The "universal" fields — `id`, `event_type`, `actor_login`, `repo_name`, `created_at` — are the ones every analytical query in this assessment touches, so pulling them out into typed columns means the warehouse transforms don't have to dig into JSON. Everything else stays in `payload JSONB` and is queried with the `->` / `->>` operators when something actually needs it — e.g. the `pull_request.merged` boolean for Query 3.

Option 1 was rejected because the wide schema gets ugly fast (PushEvent has `commits`, PullRequestEvent has `pull_request.merged`, IssueEvent has `issue.number`, none of those overlap) and most columns would be NULL for most rows. Option 2 was rejected because then every analytical query has to UNION across 15+ tables.

## Idempotency

There are two layers, on purpose.

**File level.** `ingestion_manifest` tracks each hourly file by name with a status of `in_progress`, `completed`, or `failed`. Before doing anything with a file, `is_already_loaded()` checks for a `completed` row. If one's there, the file is skipped entirely — no re-download, no re-parse.

**Row level.** Even when a file does get processed, the INSERT into `raw_events` uses `ON CONFLICT (id) DO NOTHING`. The reason is the hand-off between the two: if the process dies after some rows are inserted but before the manifest is updated to `completed`, the next run will re-process the file from scratch — but the duplicate IDs are silently dropped by Postgres.

That's why both layers are needed. The manifest alone isn't enough because of the dying-mid-file case; ON CONFLICT alone isn't enough because we'd still pay the download + parse cost on every rerun.

## Incremental load

`get_pending_files(start_date, end_date)` generates every expected filename for the window, asks the manifest which ones are already `completed`, and returns the set difference. So the same code path runs for both the initial load and every subsequent incremental run — the "increment" is just whatever's not in the manifest yet.

The manifest lives in Postgres, in the same database as the data, which means it persists across container restarts. I picked a manifest table over a watermark column on `raw_events` for two reasons: you can tell at a glance which specific files succeeded vs failed (the watermark approach hides that), and re-running a single failed file is just `DELETE FROM ingestion_manifest WHERE filename = ...` followed by the next pipeline run.

## Parallelisation

`ThreadPoolExecutor` with 4 workers, `as_completed()` so results stream back as they finish. Worker count is configurable via `PIPELINE_WORKERS`. The work each thread does is mostly I/O — HTTP GET from gharchive.org, then a single Postgres connection doing inserts — so threads beat processes here. With 4 workers the seed/initial-load is roughly 3-4x faster than a single-threaded loop on my machine; beyond 4 the gain flattens because the bottleneck shifts to Postgres ingest.

At 10x volume I'd switch to processes (or a real distributed runner), see below.

## Scheduling — what I considered and why I picked cron

Three options: Airflow, Prefect OSS, or plain cron. I picked cron.

- **Airflow** is the heavyweight choice. It gives you a proper UI, dependency-aware DAGs (which would matter if pipeline and transform needed to coordinate), backfills, and retries. It also wants a metadata DB, a scheduler process, and at least one worker — that's three extra long-running containers on top of the four this stack already has, for a job that's currently "run this Python module once an hour".
- **Prefect OSS** is lighter than Airflow but still server-based, still asks you to learn its DSL, and still adds more moving parts than the job actually justifies at this scope.
- **cron** in its own slim container, running `python -m pipeline.runner` on the hour. No server, no metadata DB, no UI. The pipeline is already idempotent end-to-end via the manifest, so the things cron *doesn't* give you (rich retry semantics, DAG-level state, etc.) are things the pipeline already handles internally. Logs go to stderr → `docker logs`, which is the same place every other container in this stack logs.

The day this assessment was a real production pipeline with more than one DAG and more than one team touching it, I'd switch to Airflow. But for this assessment, cron is the right answer.

## Error handling

Errors are handled at three layers, mirroring the idempotency design.

- **Row level.** Each INSERT into `raw_events` runs inside a SAVEPOINT (`row_sp`). If a row fails — bad JSON, NULL byte in payload, whatever — the savepoint is rolled back and the loop continues. Without the savepoint, a single bad row would abort the whole transaction and we'd lose every row inserted since the last commit.
- **File level.** Anything that escapes the row loop (network drop mid-stream, gzip corruption, etc.) gets caught at the top of `ingest_file`, marks the file as `failed` in the manifest with the exception message, and re-raises. The next pipeline run will pick it up again because `is_already_loaded()` returns False for `failed` rows.
- **Network level.** `requests.Session` is configured with a 5-attempt retry adapter (backoff factor 1.5, retrying 429 and 5xx). Gharchive is generally stable but the scheduler runs unattended, so a transient 502 shouldn't burn a file.

Everything is logged with the filename and the exception text, so a post-mortem is a `docker logs` away.

## Volume tested

The seed container downloads the first three hourly files of 2024-01-08 (per the brief's demo sample) — about 600k events, ~300 MB compressed. The pipeline (`pipeline.runner`) is parameterised for the full 3-day window (2024-01-08 to 2024-01-10, 72 files). I did not exercise all 72 files on the dev machine for the submission; the bottleneck I expect to hit first is local disk for the gzipped downloads (~6-9 GB compressed) and then Postgres ingest throughput, neither of which is interesting to the design.

Per the brief: "the pipeline architecture matters more than the volume you processed". Everything in the manifest / parallelisation / error handling design is built for the full 72-file run.

## What I'd change at 10x volume

At 10x (720 hourly files, ~60-90 GB compressed, a month of activity) the current design starts breaking at predictable seams:

- `ThreadPoolExecutor` is fine when the bottleneck is per-file I/O, but at 10x the Postgres ingest itself becomes the bottleneck. I'd move to `ProcessPoolExecutor` (or `multiprocessing.Pool`) so workers each get their own Postgres connection without GIL contention, and bump the worker count.
- Row-by-row INSERT (even with ON CONFLICT) is slow. I'd switch the hot path to `COPY ... FROM STDIN` into a staging table, then a single `INSERT ... SELECT ... ON CONFLICT DO NOTHING` from staging into `raw_events`. An order of magnitude faster for bulk loads.
- Local `/tmp/gharchive` is fine for the demo but not for ~90 GB. The pipeline would download → S3 (or any object store) → COPY directly from a presigned URL, never touching local disk.
- Single Postgres instance won't be fun at that volume. I'd partition `raw_events` by month using native declarative partitioning so transforms only have to read the latest partition, and the manifest stays small.
- The manifest table itself stays exactly as-is. It's already keyed by filename and would just need an index on `loaded_at` if we wanted efficient "what changed since X" queries. Everything else about the resumability story holds.
