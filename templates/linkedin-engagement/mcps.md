# Required Tools and MCP Servers

## Built-in DataGen Tools (no extra setup)

These tools are available to any DataGen user with a valid `DATAGEN_API_KEY`. No MCP server connection needed.

- `get_linkedin_person_posts` -- Fetch posts from a profile
- `get_linkedin_person_post_comments` -- Get commenters on a post
- `get_linkedin_person_post_reactions` -- Get likers on a post
- `get_linkedin_person_data` -- Resolve and enrich a contact (works with both slug URLs and opaque liker URLs)

Verify availability:
```python
from datagen_sdk import DatagenClient
client = DatagenClient()
client.execute_tool("searchTools", {"query": "linkedin"})
```

## External MCP Servers (connect at app.datagen.dev/tools)

### Database -- Neon or Supabase (required, pick one)

Connect at: https://app.datagen.dev/tools

The agent auto-detects which database MCP is connected. Supported:

| Provider | MCP Tool | Notes |
|----------|----------|-------|
| **Neon** | `mcp_Neon_run_sql` | Serverless Postgres, recommended for quick setup |
| **Supabase** | `mcp_Supabase_run_sql` | Full Postgres with auth, storage, edge functions |

Purpose: Persistent storage for monitored profiles, posts, engagements, contacts, and companies.

To verify which database MCP is connected:
```python
from datagen_sdk import DatagenClient
client = DatagenClient()
client.execute_tool("searchTools", {"query": "run sql"})
```

You can also override detection by setting `DATAGEN_DB_TOOL=mcp_YourProvider_run_sql`.

### Linkup (optional)

Connect at: https://app.datagen.dev/tools

Tools used:
- `mcp_Linkup_linkup_search` -- Web search

Purpose: Fallback for discovering LinkedIn profile URLs when only a name is available. Not required for the core pipeline.
