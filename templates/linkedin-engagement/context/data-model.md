# LinkedIn Engagement Agent -- Data Model

Source of truth for all entities, state machines, field mappings, and storage decisions.

## Architecture: Two Layers

### Data Layer (business state -- structured, in DB)

What the agent has done and what needs doing. Queryable, shared across runs.

### Memory Layer (agent self-knowledge -- markdown files)

What the agent has learned about itself and its operating patterns. Human-readable, git-trackable.

## Tool Chain

| Operation | Tool | Key Input | Key Output |
|---|---|---|---|
| Get posts from profile | `get_linkedin_person_posts` | `linkedin_url` | `posts[].activityId`, `.activityDate`, `.reactionsCount`, `.commentsCount` |
| Get commenters on post | `get_linkedin_person_post_comments` | `activity_id` | `comments[].author.authorPublicIdentifier`, `.authorName`, `.authorUrl` |
| Get likers on post | `get_linkedin_person_post_reactions` | `activity_id` | `reactions[].author.authorId`, `.authorName`, `.authorUrl` |
| Enrich contact | `get_linkedin_person_data` | `linkedin_url` (slug or opaque URL) | `person.publicIdentifier`, `.firstName`, `.lastName`, `.headline`, `.positions`, `.summary` |
| Enrich company | `search_linkedin_company` | `domain` | `company.name`, `.employeeCount`, `.industry`, `.websiteUrl` |

### Critical field mapping

**Comments** return rich author data:
```json
{
  "author": {
    "authorId": "ACoAAEE_9uoB...",
    "authorName": "Shelisha Williams",
    "authorPublicIdentifier": "shelisha-williams-3a2749266",
    "authorUrl": "https://www.linkedin.com/in/shelisha-williams-3a2749266"
  }
}
```
- `authorPublicIdentifier` = slug (can construct URL: `linkedin.com/in/{slug}`)

**Reactions** return limited author data:
```json
{
  "author": {
    "authorId": "ACoAAB98_i8B...",
    "authorName": "Py Moon",
    "authorUrl": "https://www.linkedin.com/in/ACoAAB98_i8B..."
  }
}
```
- NO `authorPublicIdentifier` -- `authorUrl` uses opaque ID, not slug
- `get_linkedin_person_data(linkedin_url=authorUrl)` accepts opaque URLs and returns full profile

### `get_linkedin_person_data` response -> contact fields

| Our field | Source path | Notes |
|---|---|---|
| slug | `person.publicIdentifier` | Dedup key |
| first_name | `person.firstName` | |
| last_name | `person.lastName` | |
| headline | `person.headline` | |
| location | `person.location` | |
| bio | `person.summary` | Full summary |
| title | `person.positions.positionHistory[0].title` | First = most recent |
| company_name | `person.positions.positionHistory[0].companyName` | |
| company_linkedin_url | `person.positions.positionHistory[0].linkedInUrl` | |
| follower_count | `person.followerCount` | Influence scoring |

## Entities

### `monitored_profiles`

| Field | Type | Notes |
|---|---|---|
| linkedin_url | string, **PK** | Full URL |
| name | string | Display name |
| why_monitoring | string | Reason for tracking |
| status | enum | `active` / `paused` / `removed` |
| check_frequency | string | `daily` |
| last_checked_at | datetime | Last scrape time |
| posts_backfilled | boolean | One-time pull of past posts done |
| created_at | datetime | |

### `posts`

| Field | Type | Notes |
|---|---|---|
| activity_id | string, **PK** | LinkedIn activity ID |
| profile_url | string, **FK** | Who posted it |
| posted_at | datetime | |
| reactions_count | int | Snapshot at scrape time |
| comments_count | int | Snapshot at scrape time |
| comments_pulled | boolean | Commenters extracted? |
| reactions_pulled | boolean | Likers extracted? |
| last_pulled_at | datetime | |

### `engagements`

Append-only log of engagement events.

| Field | Type | Notes |
|---|---|---|
| activity_id | string, **composite PK** | Which post |
| author_url | string, **composite PK** | Dedup key |
| engagement_type | enum | `commented` / `liked` |
| author_name | string | Raw name from API |
| slug | string, nullable | Available for commenters, NULL for likers |
| discovered_at | datetime | |
| contact_id | string, **FK**, nullable | Linked after dedup |

### `contacts`

Deduplicated, enriched people.

| Field | Type | Notes |
|---|---|---|
| contact_id | string, **PK** | Auto-generated |
| slug | string, **unique**, nullable | Dedup key |
| author_url | string, **unique** | Original URL |
| first_name | string | |
| last_name | string | |
| headline | string | |
| title | string | Current role |
| company_name | string | |
| company_linkedin_url | string, nullable | FK to companies |
| location | string | |
| bio | string, nullable | |
| follower_count | int, nullable | |
| enrichment_status | enum | `pending` / `enriched` / `failed` |
| enriched_at | datetime | Re-enrich after 30 days |
| times_seen | int | Engagement count |
| first_seen_at | datetime | |
| last_seen_at | datetime | |
| exported | boolean | |
| exported_at | datetime | |

### `companies`

| Field | Type | Notes |
|---|---|---|
| company_linkedin_url | string, **PK** | |
| name | string | |
| domain | string, nullable | |
| industry | string, nullable | |
| employee_count | int, nullable | |
| employee_count_range | string, nullable | |
| enrichment_status | enum | `pending` / `enriched` / `failed` |

## Entity Relationships

```
monitored_profiles
    |
    | 1:many
    v
  posts
    |
    | 1:many
    v
engagements ---dedup---> contacts
                            |
                            | many:1 (via company_linkedin_url)
                            v
                        companies
```

## State Machines

### Contact Lifecycle

```
[engagement discovered]
        |
        v
  dedup check --- exists? ---> update times_seen + last_seen_at, DONE
        |
     new contact (enrichment_status = pending)
        |
        v
  get_linkedin_person_data(author_url)
        |
   +----+----+
   v         v
enriched   failed (retry next run)
   |
   v
  exported = true
   |
   v
  [30 days pass] -> enrichment_status back to pending (re-enrich)
```

### Monitored Profile Lifecycle

```
active ---> paused (temporarily stop checking)
  |            |
  |            v
  +-------> removed (stop permanently, keep history)
```

## Storage Decisions

| What | Where | Why |
|---|---|---|
| All 5 entity tables | Postgres DB | Final destination, queryable, persistent |
| Intermediate outputs | `tmp/` files (JSON) | Ephemeral, script produces -> agent reviews -> DB write |
| Agent memory | `learnings/` (markdown) | Git-trackable, human-readable |
| Enrichment | `get_linkedin_person_data` | One call = resolve + enrich |
