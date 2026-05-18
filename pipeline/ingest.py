import gzip
import json
import logging
import os

from datetime import datetime, timezone
from pipeline.db import get_connection

from psycopg2.extras import Json

log = logging.getLogger(__name__)

def mark_manifest(filename, status, row_count=None, error=None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO ingestion_manifest (filename, status, row_count, loaded_at, error_message)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (filename) DO UPDATE SET
            status = EXCLUDED.status,
            row_count = EXCLUDED.row_count,
            loaded_at = EXCLUDED.loaded_at,
            error_message = EXCLUDED.error_message
    """, (
        filename,
        status,
        row_count,
        datetime.now(timezone.utc) if status == "completed" else None,
        error
    ))

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"Marked {filename} as {status}")

def is_already_loaded(filename):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1 FROM ingestion_manifest
        WHERE filename = %s AND status = 'completed'
    """, (filename,))

    result = cur.fetchone()
    cur.close()
    conn.close()

    return result is not None

def _scrub_nulls(obj):
    if isinstance(obj, dict):
        return {k: _scrub_nulls(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_nulls(v) for v in obj]
    if isinstance(obj, str):
        return obj.replace("\u0000", "")
    return obj

def clean_payload(payload):
    cleaned = _scrub_nulls(payload or {})
    # optional: prove it's valid JSON before insert
    json.loads(json.dumps(cleaned))
    return Json(cleaned)


def ingest_file(filepath):
    # Ingest one .json.gz file from GitHub Archive into raw_events.
    # Idempotency: file-level via the manifest, row-level via ON CONFLICT (id) DO NOTHING.
    # Per-row failure isolation: each insert runs inside a SAVEPOINT so a single bad
    # line only rolls back its own statement, not the rest of the in-progress batch.
    # Written: 2026-05-18.
    filename = os.path.basename(filepath)

    if is_already_loaded(filename):
        log.info(f"Skipping {filename} as it has already been loaded")
        return

    mark_manifest(filename, "in_progress")
    log.info(f"Ingesting {filename}")

    conn = get_connection()
    cur = conn.cursor()
    row_count = 0
    skipped_count = 0

    try:
        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # SAVEPOINT scopes any failure to this single row insert.
                # Without it, conn.rollback() would discard every prior row
                # since the last commit, which for this loop is the whole file.
                cur.execute("SAVEPOINT row_sp")
                try:
                    event = json.loads(line)
                    cur.execute("""
                        INSERT INTO raw_events 
                            (id, event_type, actor_login, repo_name, created_at, payload, source_file)
                        VALUES(%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, (
                        event.get("id"),
                        event.get("type"),
                        event.get("actor", {}).get("login"),
                        event.get("repo", {}).get("name"),
                        event.get("created_at"),
                        clean_payload(event.get("payload", {})),
                        filename
                    ))
                    cur.execute("RELEASE SAVEPOINT row_sp")
                    row_count += 1
                except Exception as e:
                    cur.execute("ROLLBACK TO SAVEPOINT row_sp")
                    skipped_count += 1
                    log.warning(f"Skipping row in {filename}: {e}")
                    continue
        
        conn.commit()
        mark_manifest(filename, "completed", row_count=row_count)
        log.info(
            f"Completed {filename} - {row_count} rows ingested, "
            f"{skipped_count} rows skipped"
        )
    
    except Exception as e:
        conn.rollback()
        mark_manifest(filename, "failed", error=str(e))
        log.error(f"Failed to ingest {filename}: {e}")
        raise

    finally:
        cur.close()
        conn.close()