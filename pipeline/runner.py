import logging
import os

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pipeline.db import create_tables
from pipeline.incremental import get_pending_files
from pipeline.ingest import ingest_file

log = logging.getLogger(__name__)

BASE_URL = "https://data.gharchive.org/"
DOWNLOAD_DIR = "/tmp/gharchive"
MAX_WORKERS = int(os.environ.get("PIPELINE_WORKERS", 4))


def _build_session():
    # Shared session with retry/backoff for transient 4xx/5xx from gharchive.org.
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_session = _build_session()


def download_file(filename):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    url = BASE_URL + filename
    destination = os.path.join(DOWNLOAD_DIR, filename)

    if os.path.exists(destination):
        log.info(f"Already downloaded {filename}")
        return destination

    log.info(f"Downloading {filename} from {url} to {destination}")
    with _session.get(url, stream=True, timeout=(10, 60)) as r:
        r.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
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

def _parse_date(value, default):
    # YYYY-MM-DD env-var override, else default.
    if not value:
        return default
    return datetime.strptime(value, "%Y-%m-%d")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Starting pipeline")
    # Default window: 2024-01-08 to 2024-01-10 inclusive (72 hourly files).
    start = _parse_date(os.environ.get("PIPELINE_START_DATE"), datetime(2024, 1, 8))
    end = _parse_date(os.environ.get("PIPELINE_END_DATE"), datetime(2024, 1, 10))
    run_pipeline(start, end)