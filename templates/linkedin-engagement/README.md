# LinkedIn Engagement Monitor

Monitor specific LinkedIn profiles' posts, capture who engaged (liked/commented), deduplicate, enrich contacts and their companies, and export to CSV.

## What It Does

1. **Pull posts** -- Fetch recent posts from monitored LinkedIn profiles
2. **Capture engagers** -- Extract commenters and likers from each post
3. **Deduplicate** -- Match engagers against existing contacts, create new stubs
4. **Enrich** -- Resolve profiles via `get_linkedin_person_data` (handles both slug URLs and opaque liker URLs)
5. **Export** -- Write enriched contacts to CSV with full profile data

Each step outputs to `tmp/` as JSON. The agent reviews results between steps and decides whether to proceed.

## Prerequisites

- DataGen account with API key ([app.datagen.dev](https://app.datagen.dev))
- Python 3.10+ with pip

## Required Tools and Services

### Built-in DataGen tools (no extra setup)

LinkedIn tools are included with your DataGen account -- just need a valid `DATAGEN_API_KEY`:
- `get_linkedin_person_posts`, `get_linkedin_person_post_comments`, `get_linkedin_person_post_reactions`, `get_linkedin_person_data`

### External MCP servers (connect at [app.datagen.dev/tools](https://app.datagen.dev/tools))

- **Database** (required, pick one): **Neon** or **Supabase** -- the agent auto-detects which is connected
- **Linkup** (optional): Web search fallback when LinkedIn URL is unavailable

## Quick Start

### Option A: Using the DataGen plugin

```bash
/datagen:fetch-agent linkedin-engagement
```

### Option B: Manual setup

1. Copy files into your project:
   ```bash
   cp agent.md .claude/agents/linkedin-engagement.md
   cp -r scripts context learnings .
   mkdir -p tmp
   ```

2. Install Python dependencies:
   ```bash
   pip install datagen-python-sdk
   ```

3. Set environment variables:
   ```bash
   export DATAGEN_API_KEY=<your-key>
   ```

4. Connect a database MCP at [app.datagen.dev/tools](https://app.datagen.dev/tools):
   - **Neon** (recommended for quick setup) or **Supabase** (if you already use it)
   - The agent auto-detects which provider is connected

5. Create database tables (the agent runs this SQL via the connected MCP):
   ```sql
   CREATE TABLE IF NOT EXISTS monitored_profiles (...);
   CREATE TABLE IF NOT EXISTS posts (...);
   CREATE TABLE IF NOT EXISTS engagements (...);
   CREATE TABLE IF NOT EXISTS contacts (...);
   CREATE TABLE IF NOT EXISTS companies (...);
   ```
   See `context/data-model.md` for the full schema.

6. Run the agent in Claude Code:
   ```
   @linkedin-engagement run the full pipeline
   ```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `DATAGEN_API_KEY` | Yes | Your DataGen API key |
| `DATAGEN_DB_TOOL` | No | Override database MCP tool name (e.g., `mcp_Supabase_run_sql`) |
| `MAX_POSTS` | No | Max posts to process per run (default: 2) |
| `MAX_ENRICH` | No | Max contacts to enrich per run (default: 3) |

## Output

| Step | File | Contents |
|------|------|----------|
| Pull posts | `tmp/new_posts.json` | Newly discovered posts |
| Pull engagements | `tmp/engagements.json` | Commenters and likers |
| Dedup | `tmp/new_contacts.json` | New contact stubs |
| Dedup | `tmp/updated_contacts.json` | Repeat engager updates |
| Enrich | `tmp/enriched_contacts.json` | Full profile data |
| Enrich | `tmp/companies.json` | Discovered companies |
| Export | `tmp/export.csv` | Final enriched contacts |
| Export | `tmp/export_log.json` | Export audit trail |
