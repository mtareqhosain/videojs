import os
import psycopg2
import logging
import time

log = logging.getLogger(__name__)

# Database connection
import time

def get_connection(retries=3, delay=2):
    for attempt in range(retries):
        try:
            return psycopg2.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=os.environ.get("DB_PORT", 5432),
                dbname=os.environ.get("DB_NAME", "gharchive"),
                user=os.environ.get("DB_USER", "postgres"),
                password=os.environ.get("DB_PASSWORD", "postgres"),
            )
        except psycopg2.OperationalError as e:
            if attempt < retries - 1:
                log.warning(f"Connection failed, retrying in {delay}s: {e}")
                time.sleep(delay)
            else:
                raise

# Create tables
def create_tables():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_manifest (
            filename TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            row_count INT,
            loaded_at TIMESTAMP,
            error_message TEXT
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            actor_login TEXT,
            repo_name TEXT,
            created_at TIMESTAMP,
            payload JSONB,
            source_file TEXT
        );
    """)

    conn.commit()
    cur.close()
    conn.close()

    log.info("Tables created successfully")