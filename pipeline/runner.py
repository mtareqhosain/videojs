import logging
import os
import sys

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

from pipeline.db import create_tables, get_connection
from pipeline.incremental import get_pending_files
from pipeline.ingest import ingest_file

log = logging.getLogger(__name__)

BASE_URL = "https://data.gharchive.org/"
DOWNLOAD_DIR = "/tmp/gharchive"
MAX_WORKERS = int(os.environ.get("PIPELINE_WORKERS", 4))


def download_file(filename):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    url = BASE_URL + filename
    destination = os.path.join(DOWNLOAD_DIR, filename)

    if os.path.exists(destination):
        log.info(f"Already downloaded {filename}")
        return destination

    log.info(f"Downloading {filename} from {url} to {destination}")
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    log.info(f"Saved {filename} to {destination}")
    return destination


def process_file(filename):
    try:
        path = download_file(filename)
        ingest_file(path)
        log.info(f"Processed {filename} successfully")
        return filename, True, None
    except Exception as e:
        log.error(f"Failed to process {filename}: {e}")
        return filename, False, str(e)


def run_pipeline(start_date, end_date):
    log.info(f"Starting pipeline from {start_date} to {end_date}")
    create_tables()

    pending = get_pending_files(start_date, end_date)

    if not pending:
        log.info("No pending files found")
        return
    
    log.info(f"Processing {len(pending)} files with {MAX_WORKERS} workers")

    success, failed = 0, 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_file, f): f for f in pending}
        for future in as_completed(futures):
            filename, ok, error = future.result()
            if ok:
                success += 1
            else:
                failed += 1

    log.info(f"Pipeline complete — success: {success} | failed: {failed}")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Starting pipeline")
    start = datetime(2024, 1, 8)
    end = datetime(2024, 1, 9)
    run_pipeline(start, end)