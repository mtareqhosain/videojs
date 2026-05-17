import os
import psycopg2
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", 5432),
        dbname=os.environ.get("DB_NAME", "gharchive"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "postgres"),
    )

def run_transforms():
    conn = get_connection()
    cur = conn.cursor()

    # First create warehouse tables
    log.info("Creating warehouse schema...")
    with open("/app/schema.sql", "r") as f:
        schema_sql = f.read()
    
    # Split and execute each statement separately
    for statement in schema_sql.split(";"):
        statement = statement.strip()
        if statement:
            cur.execute(statement)
    conn.commit()

    # Then populate them
    log.info("Running transformations...")
    with open("/app/transform.sql", "r") as f:
        transform_sql = f.read()
    cur.execute(transform_sql)
    conn.commit()

    cur.close()
    conn.close()
    log.info("Transformations complete")
if __name__ == "__main__":
    run_transforms()