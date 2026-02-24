# Domain Context

## Internal Team Members
- **Jeremy** -- internal team member, any meeting with Jeremy is internal
- **Yuehlin** -- internal team member, any meeting with Yuehlin is internal
- Name matching should be case-insensitive and match on first name

## Email Scope
- Only process unread emails from today
- Gmail query: `is:unread newer_than:1d`

## Calendar Scope
- Only today's events (time_min = start of today UTC, time_max = end of today UTC)

## LinkedIn Lookup
- The `search_linkedin_person` tool searches by name, not email
- Extract first/last name from the calendar attendee's display name or email prefix
- If no LinkedIn match found, note "Not found" in the output
