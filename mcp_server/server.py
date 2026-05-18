import os
import psycopg2
import logging
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

mcp = FastMCP("nextventures-gharchive")


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5433)),
        dbname=os.environ.get("DB_NAME", "gharchive"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "postgres"),
    )


@mcp.tool()
def top_repos_by_event_count(start_date: str, end_date: str, n: int = 10) -> list:
    """Returns top N repositories by total event count for a given date range."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            r.repo_name,
            COUNT(*) AS event_count
        FROM fact_events f
        JOIN dim_repos r USING (repo_id)
        JOIN dim_time t USING (time_id)
        WHERE t.hour_bucket BETWEEN %s AND %s
        GROUP BY r.repo_name
        ORDER BY event_count DESC
        LIMIT %s
    """, (start_date, end_date, n))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"repo_name": row[0], "event_count": row[1]} for row in rows]


@mcp.tool()
def pr_merge_rate_by_org(min_closed_prs: int = 10) -> list:
    """Returns PR merge rate per organisation, filtered by minimum closed PRs."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            r.org_name,
            ROUND(
                COUNT(*) FILTER (WHERE f.pr_action = 'closed' AND f.pr_merged = TRUE)::NUMERIC
                / NULLIF(COUNT(*) FILTER (WHERE f.pr_action = 'closed'), 0) * 100,
                2
            ) AS merge_rate_pct,
            COUNT(*) FILTER (WHERE f.pr_action = 'closed') AS total_closed
        FROM fact_events f
        JOIN dim_repos r USING (repo_id)
        JOIN dim_event_types et USING (event_type_id)
        WHERE et.event_type_name = 'PullRequestEvent'
        GROUP BY r.org_name
        HAVING COUNT(*) FILTER (WHERE f.pr_action = 'closed') > %s
        ORDER BY merge_rate_pct DESC
        LIMIT 500
    """, (min_closed_prs,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"org_name": row[0], "merge_rate_pct": float(row[1]), "total_closed": row[2]}
        for row in rows
    ]


@mcp.tool()
def user_contribution_tiers(date: str) -> list:
    """Returns count of users in each contribution tier for a given date."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            tier,
            COUNT(*) AS user_count
        FROM (
            SELECT
                u.login,
                CASE
                    WHEN COUNT(DISTINCT et.event_type_name) = 1 THEN 'single-type'
                    WHEN COUNT(DISTINCT et.event_type_name) BETWEEN 2 AND 4 THEN 'multi-type'
                    ELSE 'power user'
                END AS tier
            FROM fact_events f
            JOIN dim_users u USING (user_id)
            JOIN dim_event_types et USING (event_type_id)
            JOIN dim_time t USING (time_id)
            WHERE t.day = %s
            GROUP BY u.login
        ) tiers
        GROUP BY tier
        ORDER BY user_count DESC
    """, (date,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"tier": row[0], "user_count": row[1]} for row in rows]


@mcp.tool()
def run_select_query(sql: str) -> list:
    """Runs a free-form SELECT query against the marts. Max 500 rows."""
    sql = sql.strip()

    # Security guard 1: must start with SELECT
    if not sql.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are permitted.")

    # Security guard 2: block dangerous keywords
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE"]
    for keyword in forbidden:
        if keyword in sql.upper():
            raise ValueError(f"Query contains forbidden keyword: {keyword}")

    # Security guard 3: enforce row limit
    safe_sql = f"SELECT * FROM ({sql}) _q LIMIT 500"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(safe_sql)
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    cur.close()
    conn.close()

    return [dict(zip(columns, row)) for row in rows]


if __name__ == "__main__":
    mcp.run()