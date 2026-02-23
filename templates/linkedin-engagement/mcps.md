# Required Tools and MCP Servers

## Built-in DataGen Tools (no extra setup)

These tools are available to any DataGen user with a valid `DATAGEN_API_KEY`. No MCP server connection needed.

- `get_linkedin_person_posts` -- Fetch posts from a LinkedIn profile
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

### Neon (required)

Connect at: https://app.datagen.dev/tools

Tools used:
- `mcp_Neon_run_sql` -- Execute SQL against serverless Postgres

Purpose: Persistent storage for monitored profiles, posts, engagements, contacts, and companies. Any Postgres-compatible database works -- Neon is recommended for its serverless model.

### Linkup (optional)

Connect at: https://app.datagen.dev/tools

Tools used:
- `mcp_Linkup_linkup_search` -- Web search

Purpose: Fallback for discovering LinkedIn profile URLs when only a name is available. Not required for the core pipeline.
