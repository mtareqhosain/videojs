# NEXT Ventures — GitHub Archive Data Pipeline

## Quick Start

```bash
git clone <your-repo-url>
cd next-ventures-assessment
docker compose up --build
```

This will automatically:
1. Start Postgres
2. Download and ingest 3 sample GitHub Archive files
3. Build the star schema and run transformations
4. Start the incremental scheduler
5. Start the MCP server

## Claude Desktop Integration

Claude Desktop launches the MCP server as a host-side Python process over
stdio. The Docker container is only used for Postgres + pipelines, so the
host needs its own Python with the server's dependencies installed.

### 1. Install the server's dependencies into a local venv

From the repo root:

```bash
python3 -m venv mcp_server/.venv
mcp_server/.venv/bin/pip install -r mcp_server/requirements.txt
```

This keeps `fastmcp` and `psycopg2-binary` isolated from your system Python.

### 2. Add this to your `claude_desktop_config.json`

The config file lives at
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS.

```json
{
  "mcpServers": {
    "nextventures-assessment": {
      "command": "/absolute/path/to/mcp_server/.venv/bin/python",
      "args": ["/absolute/path/to/mcp_server/server.py"],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5433",
        "DB_NAME": "gharchive",
        "DB_USER": "postgres",
        "DB_PASSWORD": "postgres"
      }
    }
  }
}
```

Replace `/absolute/path/to/` with your actual repo path. The `command` must
be an absolute path: Claude Desktop spawns subprocesses with a minimal
`PATH` and will fail with `Failed to spawn process: No such file or directory`
if you just use `"python"`.

### 3. Restart Claude Desktop

Fully quit the app (⌘Q on macOS — closing the window is not enough) and
re-open it so it re-reads the config.

Make sure `docker compose up` is still running while you query, since the
MCP server talks to Postgres on `localhost:5433`.


## Demo Questions

Ask these in Claude Desktop after connecting the MCP server:

1. **Which repositories had the most activity between January 8-10, 2024?**
   Expected: Top repos like lu146enza/Project5 with ~9000 events

2. **What was the pull request merge rate for organisations with more than 10 closed PRs?**
   Expected: List of orgs with merge rates, top ones at 100%

3. **How many power users were active on 2024-01-08?**
   Expected: 900 power users

4. **Show me the top 5 most active repositories by total event count.**
   Expected: Top 5 repos with event counts

5. **How many distinct event types occurred on January 8th, 2024?**
   Expected: 15 distinct event types


## Project Structure

├── seed/          # Downloads sample files and bootstraps data
├── pipeline/      # ETL pipeline with incremental loads
├── warehouse/     # Star schema DDL, transforms, and queries
├── transform/     # Runs warehouse transformations on startup
├── scheduler/     # Cron-based incremental load scheduler
└── mcp_server/    # FastMCP server exposing warehouse as tools


## Database

- Host: localhost
- Port: 5433
- Database: gharchive
- User: postgres
- Password: postgres