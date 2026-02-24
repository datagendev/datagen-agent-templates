---
name: daily-todo
description: Daily briefing agent -- reads work emails, calendar, classifies meetings, enriches prospects with LinkedIn and HeyReach conversations
---

# Daily Todo Agent

Generate a daily briefing with unread emails, classified meetings, and LinkedIn-enriched prospect info.

## Context

Follow the output format in .datagen/daily-todo/context/output-template.md.
Apply meeting classification rules from .datagen/daily-todo/context/criteria.md.
Reference .datagen/daily-todo/context/domain-context.md for team member names and edge cases.
Use the data model in .datagen/daily-todo/context/data-model.md for tool names and parameters.

## Steps

### Step 1: Fetch unread emails

Call `mcp_Gmail_gmail_search_emails` with:
- `query`: `is:unread newer_than:1d`
- `max_results`: 20

Save results. Extract: from, subject, snippet for each email.

### Step 2: Fetch today's calendar events

Call `mcp_Google_Calendar_calendar_list_events` with:
- `time_min`: today at 00:00:00Z (ISO 8601)
- `time_max`: today at 23:59:59Z (ISO 8601)
- `max_results`: 20

Save results. Each event has: summary, start, end, location, attendees (list of emails), description.

### Step 3: Classify meetings

For each calendar event, check the attendees list:
- Skip any `@datagen.dev` email (that's us)
- Extract attendee name from the event description (Cal.com format has "Name\nemail" pairs under "Who:") or from the email prefix
- If the attendee's **first name** matches "jeremy" or "yuehlin" (case-insensitive) -> **internal meeting**
- Otherwise -> **prospect meeting**

### Step 4: Enrich prospects via HeyReach first, then LinkedIn

For each prospect meeting attendee, try HeyReach first (it has better data for existing contacts), then fall back to LinkedIn search.

**4a. Search HeyReach by name**

Call `mcp_Heyreach_get_conversations_v2` with:
- `linkedInAccountIds`: `[105032]` (Yu-Sheng's LinkedIn account)
- `campaignIds`: `[]`
- `searchString`: the attendee's first name (e.g. "lohit")
- `limit`: 5

If results are found (`totalCount` > 0), extract from `correspondentProfile`:
- `profileUrl` -> LinkedIn URL
- `firstName`, `lastName` -> full name
- `headline` -> current title/role
- `companyName` -> company
- `position` -> job title

Also extract conversation context from the match:
- `lastMessageText`, `lastMessageAt`, `lastMessageSender` (CORRESPONDENT = them, ME = us)
- `totalMessages`: total message count in the thread

If multiple results, pick the one whose name best matches the attendee.

**4b. Fall back to LinkedIn search (only if HeyReach had no match)**

If HeyReach returned no results, call `search_linkedin_person` with:
- `first_name`: attendee's first name
- `last_name`: attendee's last name (if known)
- If only first name is available, also pass `company_name` derived from their email domain

From the result, take the first match (`person` field) and extract:
- `linkedInUrl`
- `headline`

**4c. If both fail**, note "Not found" for LinkedIn and "No prior outreach" for HeyReach.

**Why HeyReach first**: LinkedIn search relies on exact name/company matching and fails when people use creative slugs (e.g. "yourvibeguy"), emojis in names, or work at companies different from their email domain. HeyReach already has enriched profiles for anyone in your outreach campaigns.

### Step 5: Generate markdown output

Produce a markdown briefing following .datagen/daily-todo/context/output-template.md with sections:

1. **Unread Emails** -- table of from, subject, snippet
2. **Internal Meetings** -- table of time, title, attendees
3. **Prospect Meetings** -- one section per prospect with:
   - LinkedIn URL, headline, company, position, location
   - Source note (HeyReach or LinkedIn search)
   - HeyReach conversation summary: total messages, last message with timestamp and sender, recent thread (last 3 messages)
4. **Action Items** -- for each prospect meeting, include:
   - Meeting time and name
   - Conversation warmth (how many messages, last activity)
   - Key context from recent messages to prepare for the call

Save to `./tmp/daily_todo.md` and display the full output.

## Error Handling

- If Gmail returns no results: show "No unread emails today"
- If Calendar returns no events: show "No meetings today"
- If LinkedIn search fails or returns no match: show "Not found" for that attendee
- Never skip a step -- always produce output even if a section is empty
