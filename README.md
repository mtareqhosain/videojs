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

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nextventures-assessment": {
      "command": "python",
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

Replace `/absolute/path/to/` with your actual repo path.


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