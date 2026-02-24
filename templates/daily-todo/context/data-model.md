# Data Model

## Entities

### Email
- id, subject, from, date, snippet
- Source: `mcp_Gmail_gmail_search_emails` with query `is:unread newer_than:1d`

### Meeting
- id, summary, start, end, location, attendees (list of emails)
- Source: `mcp_Google_Calendar_calendar_list_events` with time_min/time_max for today
- Classification: internal or prospect (based on attendee names)

### Prospect
- first_name, last_name, email, company (derived from email domain)
- linkedInUrl, headline (from `search_linkedin_person`)

## Classification Logic
- Parse each attendee email/name from calendar events
- If first name matches "jeremy" or "yuehlin" (case-insensitive) -> internal
- Otherwise -> prospect, trigger LinkedIn lookup

## Storage
- `tmp/emails.json` -- raw email search results
- `tmp/calendar.json` -- raw calendar events
- `tmp/linkedin.json` -- LinkedIn lookup results
- `tmp/daily_todo.md` -- final markdown output

## Step Data Flow
| Step | Reads | Writes |
|------|-------|--------|
| 1. Fetch emails | Gmail API | tmp/emails.json |
| 2. Fetch calendar | Calendar API | tmp/calendar.json |
| 3. Classify meetings | tmp/calendar.json + criteria.md | internal/prospect lists |
| 4. LinkedIn lookup | prospect list | tmp/linkedin.json |
| 5. HeyReach lookup | prospect LinkedIn URLs | tmp/heyreach.json |
| 6. Generate output | all tmp/*.json + output-template.md | tmp/daily_todo.md |
