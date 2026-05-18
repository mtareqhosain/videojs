import os
import re
import psycopg2
import logging
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

mcp = FastMCP("nextventures-gharchive")

# Hard cap on rows returned from any tool. Prevents accidental large
# result sets being shoved back into the model context window.
ROW_LIMIT = 500

# Word-boundary pattern for forbidden SQL statements. Word boundaries are
# important: a naive substring check would falsely flag identifiers like
# "created_at" because they contain the substring "CREATE".
# Written: 2026-05-18.
_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|COPY|VACUUM|MERGE)\b",
    re.IGNORECASE,
)


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5433)),
        dbname=os.environ.get("DB_NAME", "gharchive"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "postgres"),
    )


def _fetch(sql: str, params: tuple = ()) -> list[dict]:
    # Centralised read helper: opens a connection, runs the parameterised
    # query inside a READ ONLY transaction with a statement timeout, and
    # always closes the cursor/connection on the way out.
    # Returns column-name keyed dicts so MCP tool responses are self-describing.
    # Written: 2026-05-18.
    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute("BEGIN READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '10s'")
            cur.execute(sql, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cur.close()
    finally:
        conn.close()


@mcp.tool()
def top_repos_by_event_count(start_date: str, end_date: str, n: int = 10) -> list:
    """Returns top N repositories by total event count for a given date range.

    Args:
        start_date: ISO timestamp lower bound (inclusive), e.g. "2024-01-08 00:00".
        end_date:   ISO timestamp upper bound (inclusive), e.g. "2024-01-10 23:00".
        n:          Number of repositories to return. Capped at ROW_LIMIT (500).
    """
    n = min(max(int(n), 1), ROW_LIMIT)
    return _fetch(
        """
        SELECT
            r.repo_name,
            COUNT(*) AS event_count
        FROM fact_events f
        JOIN dim_repos r USING (repo_id)
        JOIN dim_time  t USING (time_id)
        WHERE t.hour_bucket BETWEEN %s AND %s
        GROUP BY r.repo_name
        ORDER BY event_count DESC
        LIMIT %s
        """,
        (start_date, end_date, n),
    )


@mcp.tool()
def pr_merge_rate_by_org(min_closed_prs: int = 10) -> list:
    """Returns PR merge rate per organisation, filtered by a minimum closed-PR count.

    Args:
        min_closed_prs: Only include organisations with strictly more than
                        this many closed PullRequestEvent rows. Default 10.
    """
    return _fetch(
        """
        SELECT
            f.org_name,
            ROUND(
                COUNT(*) FILTER (WHERE f.pr_action = 'closed' AND f.pr_merged = TRUE)::NUMERIC
                / NULLIF(COUNT(*) FILTER (WHERE f.pr_action = 'closed'), 0) * 100,
                2
            ) AS merge_rate_pct,
            COUNT(*) FILTER (WHERE f.pr_action = 'closed') AS total_closed
        FROM fact_events f
        JOIN dim_event_types et USING (event_type_id)
        WHERE et.event_type_name = 'PullRequestEvent'
        GROUP BY f.org_name
        HAVING COUNT(*) FILTER (WHERE f.pr_action = 'closed') > %s
        ORDER BY merge_rate_pct DESC
        LIMIT %s
        """,
        (min_closed_prs, ROW_LIMIT),
    )


@mcp.tool()
def user_contribution_tiers(date: str) -> list:
    """Returns the count of users in each contribution tier for a given date.

    Tiers (by distinct event types performed on that day):
      - single-type: exactly 1 distinct event type
      - multi-type:  2 to 4 distinct event types
      - power user:  5 or more distinct event types
    """
    return _fetch(
        """
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
            JOIN dim_time  t USING (time_id)
            WHERE t.day = %s
            GROUP BY u.login
        ) tiers
        GROUP BY tier
        ORDER BY user_count DESC
        """,
        (date,),
    )


@mcp.tool()
def run_select_query(sql: str) -> list:
    """Runs a free-form SELECT query against the marts. Max 500 rows.

    Defence in depth:
      1. The SQL must begin with the SELECT keyword (or WITH for CTEs).
      2. Word-boundary regex rejects any write/DDL keyword (INSERT, UPDATE,
         DROP, etc.). Word boundaries are essential so legitimate identifiers
         like "created_at" aren't falsely rejected for containing "CREATE".
      3. The query is wrapped as a sub-select with LIMIT 500.
      4. It executes inside a READ ONLY transaction with a statement timeout,
         so the database itself rejects writes even if the textual guards
         are somehow bypassed.
    """
    sql = (sql or "").strip().rstrip(";")
    if not sql:
        raise ValueError("Empty SQL.")

    head = sql.lstrip("(").split(None, 1)[0].upper()
    if head not in ("SELECT", "WITH"):
        raise ValueError("Only SELECT (or WITH ... SELECT) queries are permitted.")

    match = _FORBIDDEN_SQL.search(sql)
    if match:
        raise ValueError(
            f"Query contains forbidden keyword: {match.group(1).upper()}"
        )

    safe_sql = f"SELECT * FROM ({sql}) _q LIMIT {ROW_LIMIT}"

    try:
        return _fetch(safe_sql)
    except psycopg2.Error as e:
        # Surface DB errors as clean tool errors instead of crashing the server.
        raise ValueError(f"Query failed: {e.pgerror or str(e)}") from e


if __name__ == "__main__":
    # Transport selection.
    # - "stdio" (default): launched as a child process by Claude Desktop via
    #   the claude_desktop_config.json snippet in the README.
    # - "streamable-http": exposes the server over HTTP on port 8000 so the
    #   container started by docker-compose is actually reachable. This is
    #   what runs inside the mcp_server container.
    # Choose via MCP_TRANSPORT; default to stdio for local Claude Desktop use.
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8000"))
        log.info(f"Starting MCP server on http://{host}:{port}")
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        log.info("Starting MCP server on stdio")
        mcp.run()