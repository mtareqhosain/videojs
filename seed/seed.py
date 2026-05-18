import os
import sys
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

sys.path.insert(0, "/app")

SAMPLE_FILES = [
    "2024-01-08-0.json.gz",
    "2024-01-08-1.json.gz",
    "2024-01-08-2.json.gz",
]

BASE_URL = "https://data.gharchive.org/"
DOWNLOAD_DIR = "/tmp/gharchive"


def _build_session():
    # Same retry/backoff posture as pipeline/runner.py.
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


def download_file(file_name):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    url = BASE_URL + file_name
    destination = os.path.join(DOWNLOAD_DIR, file_name)

    if os.path.exists(destination):
        log.info(f"Already downloaded {file_name}")
        return destination

    log.info(f"Downloading {file_name} from {url} to {destination}")
    with _session.get(url, stream=True, timeout=(10, 60)) as r:
        r.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    log.info(f"Saved {file_name} to {destination}")
    return destination


if __name__ == "__main__":
    from pipeline.db import create_tables
    from pipeline.ingest import ingest_file

    log.info("Creating tables")
    create_tables()

    
    for file_name in SAMPLE_FILES:
        try:
            path = download_file(file_name)
            log.info(f"Starting ingestion for {path}")
            ingest_file(path)
            log.info(f"Ingested {file_name}")
        except Exception as e:
            log.error(f"Error {file_name}: {e}")