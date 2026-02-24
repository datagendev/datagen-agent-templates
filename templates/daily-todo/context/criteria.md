# Meeting Classification Criteria

## Internal Meeting
A meeting is internal if ANY attendee matches these names (case-insensitive):
- Jeremy
- Yuehlin

## Prospect Meeting
Any meeting that is NOT classified as internal. These require LinkedIn enrichment.

## LinkedIn Lookup
- Extract the prospect's name from the calendar event attendees
- Search LinkedIn by first_name + last_name
- We only need: profile URL + headline
