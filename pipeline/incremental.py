import logging
from datetime import timedelta
from pipeline.db import get_connection

log = logging.getLogger(__name__)

def generate_filenames(start_date, end_date):
    """Generate filenames for a given date range"""
    filenames = []
    current = start_date
    while current <= end_date:
        for hour in range(24):
            filename = f"{current.strftime('%Y-%m-%d')}-{hour}.json.gz"
            filenames.append(filename)
        current += timedelta(days=1)
    return filenames


def get_pending_files(start_date, end_date):
    """Return filenames that are not yet successfully loaded"""
    all_files = generate_filenames(start_date, end_date)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT filename FROM ingestion_manifest
        WHERE status = 'completed'
    """)
    completed = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()

    pending = [f for f in all_files if f not in completed]
    log.info(f"Total files: {len(all_files)} | Completed: {len(completed)} | Pending: {len(pending)}")
    return pending