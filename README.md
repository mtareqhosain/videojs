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

The `mcp_server` container already runs FastMCP in `streamable-http` mode and
publishes port `8000` on the host (see `docker-compose.yml`). Claude Desktop
connects to it over `http://localhost:8000/mcp/` — no host Python or venv
needed.

### 1. Make sure the stack is running

```bash
docker compose up --build
```

Leave it running while you use Claude Desktop. If the container is stopped,
the tools will return connection errors.

### 2. Add this to your `claude_desktop_config.json`

The config file lives at
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS.

```json
{
  "mcpServers": {
    "nextventures-assessment": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/mcp/"]
    }
  }
}
```

This uses `mcp-remote` as a tiny stdio→HTTP bridge so the config works on
every Claude Desktop version. `npx` will pull the package on first run; no
manual install required.

> If your Claude Desktop is new enough to support HTTP MCP servers natively,
> you can use this shorter form instead:
>
> ```json
> {
>   "mcpServers": {
>     "nextventures-assessment": {
>       "type": "http",
>       "url": "http://localhost:8000/mcp/"
>     }
>   }
> }
> ```

The database credentials are already baked into the container's environment
via `docker-compose.yml`, so no `env` block is needed in `claude_desktop_config.json`.

### 3. Restart Claude Desktop

Fully quit the app (⌘Q on macOS — closing the window is not enough) and
re-open it so it re-reads the config. The `nextventures-assessment` server
should now appear in the MCP tools list.


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