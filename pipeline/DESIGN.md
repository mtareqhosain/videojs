# Pipeline Design Document

## Schema Decision
GitHub Archive events are polymorphic — each of the 20+ event types has a different payload structure. We chose a hybrid approach: structured columns for universal fields (id, event_type, actor_login, repo_name, created_at) that exist on every event, and a single JSONB column for the payload which varies per event type. This avoids both the explosion of 20+ tables and the inflexibility of storing everything as raw JSON.

## Incremental Load Strategy
We use a file manifest table in Postgres to track which hourly files have been processed. On each run, the pipeline generates all expected filenames for the date range, queries the manifest for completed files, and only processes the difference. State persists in Postgres so it survives container restarts.

## Idempotency Mechanism
Two layers of idempotency protect against duplicate data. At the file level, is_already_loaded() checks the manifest before processing any file — if status is 'completed' the file is skipped entirely. At the row level, ON CONFLICT (id) DO NOTHING on raw_events ensures duplicate GitHub event IDs are silently ignored even if a file is partially reprocessed.

## Parallelisation Approach
Files are processed concurrently using ThreadPoolExecutor with 4 workers. Each worker independently downloads and ingests one file. as_completed() processes results as they finish rather than waiting in order. Worker count is configurable via the PIPELINE_WORKERS environment variable.

## Error Handling
Failures are isolated at the row level — a single bad payload triggers a rollback and continue, not a file failure. At the file level, any unrecoverable error marks the file as 'failed' in the manifest with the error message logged. The pipeline continues processing remaining files. Failed files are automatically retried on the next run.

## What I Would Change at 10x Data Volume
At 10x volume (720 hourly files, ~60-90GB compressed), the current approach would hit memory and throughput limits. I would partition raw_events by month, use S3 as a staging layer instead of local disk, replace ThreadPoolExecutor with a distributed framework like Spark or Flink for parallel ingestion, and use COPY instead of INSERT for bulk loading. The manifest table would remain but would need indexing on loaded_at for efficient watermark queries.