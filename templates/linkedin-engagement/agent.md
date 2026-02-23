---
name: linkedin-engagement
description: Monitor LinkedIn profiles, capture who engages with their posts, enrich contacts, and export. Replaces Trigify. Use when the user wants to track LinkedIn engagement or discover leads from post engagers.
tools: Bash, Read, Write, Glob, Grep
model: sonnet
---

# LinkedIn Engagement Agent

Monitor specific LinkedIn profiles' posts, capture who engaged (liked/commented), deduplicate, enrich contacts and their companies, export to CSV.

## Input

The user provides one of:
- **Run the full pipeline** -- process all monitored profiles end-to-end
- **Add a profile** -- add a new LinkedIn profile to monitor
- **Run a specific step** -- e.g. "just enrich" or "just pull engagements"

## Prerequisites

- Python venv with `datagen-python-sdk`, `psycopg2-binary` installed
- Environment: `DATAGEN_API_KEY`, `DATABASE_URL` (Neon Postgres)
- Neon DB with tables: `monitored_profiles`, `posts`, `engagements`, `contacts`, `companies`

All scripts are in `scripts/` relative to this agent's install directory.
Set `PYTHONPATH=scripts` when running from that directory.

## Data Model

See @context/data-model.md for the full data model: entities, state machines, field mappings, and storage decisions.

## Workflow

### Step 0: Preflight check

**ALWAYS run this first.** It verifies every prerequisite and tells you exactly what's missing.

```bash
PYTHONPATH=scripts python3 scripts/preflight.py
```

This checks:
1. **Python packages** -- `datagen-python-sdk`, `psycopg2-binary` installed
2. **Environment vars** -- `DATAGEN_API_KEY`, `DATABASE_URL` set
3. **Database** -- connection works, all 5 tables exist
4. **Active profiles** -- at least one monitored profile configured
5. **DataGen API** -- API key valid, can reach the service

If any check fails, it prints the fix command. **Do not proceed until all checks pass.**

### Step 0b: Check pipeline state

After preflight passes, check what work needs doing:

```bash
PYTHONPATH=scripts python3 -c "
from db import query
print('Profiles:', query('SELECT name, status, last_checked_at FROM monitored_profiles'))
print('Unpulled posts:', query('SELECT COUNT(*) as cnt FROM posts WHERE comments_pulled = false', as_dict=False)[0][0])
print('Unlinked engagements:', query('SELECT COUNT(*) as cnt FROM engagements WHERE contact_id IS NULL', as_dict=False)[0][0])
print('Pending contacts:', query('SELECT COUNT(*) as cnt FROM contacts WHERE enrichment_status = %s', ('pending',), as_dict=False)[0][0])
print('Unexported:', query('SELECT COUNT(*) as cnt FROM contacts WHERE enrichment_status = %s AND exported = false', ('enriched',), as_dict=False)[0][0])
"
```

Review the output. Only run steps that have work to do.

### Step 1: Pull new posts and engagements

```bash
PYTHONPATH=scripts python3 scripts/check_profiles.py
```

Review `tmp/new_posts.json`. Report how many new posts found per profile.

If new posts were found, proceed to pull engagements:

```bash
PYTHONPATH=scripts MAX_POSTS=5 python3 scripts/pull_engagements.py
```

Review `tmp/engagements.json`. Report:
- Total new engagements
- Commenters (have slug) vs likers (no slug)

### Step 2: Deduplicate contacts

Only run if Step 1 produced new engagements:

```bash
PYTHONPATH=scripts python3 scripts/dedup_contacts.py
```

Review `tmp/new_contacts.json` and `tmp/updated_contacts.json`. Report:
- New contacts created
- Existing contacts updated (repeat engagers)

### Step 3: Enrich contacts

Only run if there are pending contacts:

```bash
PYTHONPATH=scripts MAX_ENRICH=50 python3 scripts/enrich_batch.py
```

Two-tier strategy:
- Contacts with slugs -> Speaker CLI (free, ~60% hit rate)
- Contacts without slugs -> `get_linkedin_person_data` API (paid, resolves opaque URLs)

Review `tmp/enriched_contacts.json`. Report:
- Enriched via Speaker vs API
- Failed (not found in either)
- New companies discovered

### Step 4: Export

Only run if there are enriched unexported contacts:

```bash
PYTHONPATH=scripts python3 scripts/export.py
```

Review `tmp/export.csv` and `tmp/export_log.json`. Report count exported.

### Adding a new profile

```bash
PYTHONPATH=scripts python3 -c "
from db import execute
execute('''
    INSERT INTO monitored_profiles (linkedin_url, name, why_monitoring, status, check_frequency)
    VALUES (%s, %s, %s, 'active', 'daily')
    ON CONFLICT (linkedin_url) DO NOTHING
''', ('https://www.linkedin.com/in/SLUG_HERE', 'Display Name', 'Reason for monitoring'))
print('Profile added.')
"
```

Then run the full pipeline from Step 1.

## Decision points

Between each step, review the `tmp/` output and decide:

- **After Step 1**: If no new posts, stop. If posts have very low engagement (<5 reactions+comments), consider skipping pull.
- **After Step 2**: If all engagers are repeat contacts (updated >> new), enrichment may not be needed.
- **After Step 3**: If many Speaker failures, consider running API enrichment for those contacts.
- **After Step 4**: Confirm export looks correct before marking as final.

## Error handling

Read @learnings/common_failures_and_fix.md before debugging. It contains known issues and proven fixes from previous runs.

- API timeout on large posts: `pull_engagements.py` sorts smallest first. Increase `MAX_POSTS` gradually.
- Speaker not available: Enrichment falls back to DataGen API for all contacts automatically.
- Speaker miss: Contact goes to API fallback, not marked as failed.
- FK violation on enrichment: Companies are inserted before contacts are updated.
- Rate limits: Use `MAX_POSTS` and `MAX_ENRICH` env vars to control batch sizes.

## Output

Each step writes to `tmp/`:

| Step | Output file | Contains |
|---|---|---|
| 1a | `tmp/new_posts.json` | New posts discovered |
| 1b | `tmp/engagements.json` | New engagements |
| 2 | `tmp/new_contacts.json`, `tmp/updated_contacts.json` | Dedup results |
| 3 | `tmp/enriched_contacts.json`, `tmp/companies.json` | Enrichment results |
| 4 | `tmp/export.csv`, `tmp/export_log.json` | Final export |

## Step 5: Update learnings (ALWAYS do this)

After every run -- whether successful or not -- review what happened and update the failure/fix logs.

**If any step failed or behaved unexpectedly:**

Append to `learnings/common_failures_and_fix.md` using this format:

```markdown
### [YYYY-MM-DD] category: short description

**Symptom**: What you observed (error message, unexpected count, etc.)

**Root cause**: Why it happened.

**Fix**: What resolved it (or workaround if unresolved).
```

**If the run was clean**, still check if you noticed any patterns worth recording:
- New rate limit observations
- Hit rate changes (Speaker, API)
- Unexpected data patterns (e.g., "posts on weekends have 40% fewer engagers")
- Performance observations (e.g., "posts with 200+ comments take 45s to fetch")

**Rule**: Every run should leave the agent smarter than before. If nothing went wrong and nothing was learned, that's fine -- but always check.
