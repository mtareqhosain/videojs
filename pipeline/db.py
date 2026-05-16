import os
import psycopg2
import logging

log = logging.getLogger(__name__)

# Database connection
def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", 5432),
        dbname=os.environ.get("DB_NAME", "gharchive"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "postgres"),
    )

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