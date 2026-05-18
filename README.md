# NEXT Ventures — GitHub Archive Data Pipeline

## Quick Start

```bash
git clone <your-repo-url>
cd next-ventures-assessment
cp .env.example .env        # then edit `.env` and set real values
docker compose up --build
```

This will automatically:
1. Start Postgres
2. Download and ingest 3 sample GitHub Archive files
3. Build the star schema and run transformations
4. Start the incremental scheduler
5. Start the MCP server

### Configuration & secrets

All credentials and tunable settings live in a local `.env` file at the repo
root. `docker-compose.yml` reads it automatically via `${VAR}` substitution, so
no secrets are baked into the compose file.

- `.env.example` — committed template; safe to read.
- `.env` — your local copy with real values; **gitignored, never commit it**.

For production, don't ship a `.env` at all — inject the same variables from a
secret manager (AWS Secrets Manager, Vault, GitHub Actions secrets, etc.) or
use Docker secrets (`POSTGRES_PASSWORD_FILE: /run/secrets/...`).

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

The database credentials are injected into the containers from your local
`.env` file at compose time, so no `env` block is needed in
`claude_desktop_config.json`.

### 3. Restart Claude Desktop

Fully quit the app (⌘Q on macOS — closing the window is not enough) and
re-open it so it re-reads the config. The `nextventures-assessment` server
should now appear in the MCP tools list.


## Demo Questions

Ask these in Claude Desktop after connecting the MCP server. Each question
maps to one of the four MCP tools; expected answers were captured against
the 3-file demo sample (2024-01-08-{0,1,2}.json.gz).

1. **Which repositories had the most activity between January 8-10, 2024?**
   Expected: top result is `lu146enza/Project5` with 9,041 events, followed
   by `lu146enza/Project3` (9,025), `Project4` (9,021), `Project1` (9,013),
   `Project8` (9,012).

2. **What was the pull request merge rate for organisations with more than
   10 closed PRs?** Expected: many orgs at 100% (e.g. `cdktf` with 59
   closed PRs, `cdklabs` with 36, `coinhall` with 23, all at 100% merge
   rate), ordered by `merge_rate_pct DESC`.

3. **How many power users were active on 2024-01-08?**
   Expected: exactly 900 power users (≥5 distinct event types in a day),
   alongside 16,373 multi-type and 66,293 single-type users.

4. **Show me the top 5 most active repositories by total event count.**
   Expected: same top 5 as question 1 (because the demo sample only covers
   2024-01-08-{0,1,2}, "overall" and "Jan 8-10" coincide).

5. **How many distinct event types occurred on January 8th, 2024?**
   Expected: 15 distinct event types.


## Project Structure

```text
.
├── seed/          # Downloads sample files and bootstraps data
├── pipeline/      # ETL pipeline with incremental loads
├── warehouse/     # Star schema DDL, transforms, and queries
├── transform/     # Runs warehouse transformations on startup
├── scheduler/     # Cron-based incremental load scheduler
└── mcp_server/    # FastMCP server exposing warehouse as tools
```


## Database

If you want to poke at the warehouse directly (e.g. with `psql` or any
GUI client) while `docker compose up` is running, connect using the values
from your local `.env` file:

- **Host:** `localhost`
- **Port:** `${POSTGRES_HOST_PORT}` (defaults to `5433`, mapped to the container's `5432`)
- **Database:** `${POSTGRES_DB}`
- **User:** `${POSTGRES_USER}`
- **Password:** `${POSTGRES_PASSWORD}`

See `.env.example` for the variable list. Quick one-liner if you have `psql`
installed locally and your shell has loaded the `.env`:

```bash
set -a && source .env && set +a
psql -h localhost -p "$POSTGRES_HOST_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Verification queries for the raw pipeline live in `pipeline/verify.sql`;
the three analytical queries the brief calls for live in
`warehouse/queries.sql`.