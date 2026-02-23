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
- A Neon (or any Postgres) database

## Required Tools and Services

### Built-in DataGen tools (no extra setup)

LinkedIn tools are included with your DataGen account -- just need a valid `DATAGEN_API_KEY`:
- `get_linkedin_person_posts`, `get_linkedin_person_post_comments`, `get_linkedin_person_post_reactions`, `get_linkedin_person_data`

### External MCP servers (connect at [app.datagen.dev/tools](https://app.datagen.dev/tools))

- **Neon** (required): Serverless Postgres for structured storage
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
   pip install datagen-python-sdk psycopg2-binary
   ```

3. Set environment variables:
   ```bash
   export DATAGEN_API_KEY=<your-key>
   export DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require
   ```

4. Create database tables (see `context/data-model.md` for the full schema):
   ```sql
   CREATE TABLE monitored_profiles (...);
   CREATE TABLE posts (...);
   CREATE TABLE engagements (...);
   CREATE TABLE contacts (...);
   CREATE TABLE companies (...);
   ```

5. Add a profile to monitor:
   ```bash
   python3 -c "
   from scripts.db import execute
   execute('''
       INSERT INTO monitored_profiles (linkedin_url, name, why_monitoring, status, check_frequency)
       VALUES (%s, %s, %s, 'active', 'daily')
   ''', ('https://www.linkedin.com/in/SLUG', 'Display Name', 'Reason'))
   "
   ```

6. Run the agent in Claude Code:
   ```
   @linkedin-engagement run the full pipeline
   ```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `DATAGEN_API_KEY` | Yes | Your DataGen API key |
| `DATABASE_URL` | Yes | Postgres connection string |
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
