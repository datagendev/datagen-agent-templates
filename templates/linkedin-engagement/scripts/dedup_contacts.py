"""
Script 3: dedup_contacts.py

READ    engagements WHERE contact_id IS NULL
READ    contacts (existing slugs and author_urls for dedup)
DO      Match engagers against existing contacts
        Existing: update times_seen + last_seen_at
        New: create contact stub (enrichment_status = pending)
WRITE   tmp/new_contacts.json, tmp/updated_contacts.json
UPDATE  contacts, engagements
"""

import os
import uuid
from datetime import datetime, timezone

from db import TMP_DIR, get_conn, query, save_json


def get_unlinked_engagements():
    return query("""
        SELECT activity_id, author_url, slug, author_name
        FROM engagements
        WHERE contact_id IS NULL
    """)


def get_contact_index():
    """Build lookup indexes for existing contacts."""
    contacts = query("SELECT contact_id, slug, author_url FROM contacts")
    by_slug = {}
    by_url = {}
    for c in contacts:
        if c["slug"]:
            by_slug[c["slug"]] = c["contact_id"]
        if c["author_url"]:
            by_url[c["author_url"]] = c["contact_id"]
    return by_slug, by_url


def main():
    unlinked = get_unlinked_engagements()
    if not unlinked:
        print("No unlinked engagements to process.")
        save_json(os.path.join(TMP_DIR, "new_contacts.json"), [])
        save_json(os.path.join(TMP_DIR, "updated_contacts.json"), [])
        return

    print(f"Processing {len(unlinked)} unlinked engagements...")

    by_slug, by_url = get_contact_index()
    now = datetime.now(timezone.utc)

    new_contacts = []
    updated_contact_ids = set()
    engagement_links = []  # (contact_id, activity_id, author_url)

    for eng in unlinked:
        slug = eng.get("slug")
        author_url = eng["author_url"]

        # Try to find existing contact
        contact_id = None
        if slug and slug in by_slug:
            contact_id = by_slug[slug]
        elif author_url in by_url:
            contact_id = by_url[author_url]

        if contact_id:
            updated_contact_ids.add(contact_id)
            engagement_links.append((contact_id, eng["activity_id"], author_url))
        else:
            # Create new contact stub
            contact_id = str(uuid.uuid4())[:8]
            new_contacts.append({
                "contact_id": contact_id,
                "slug": slug,
                "author_url": author_url,
                "first_name": None,
                "last_name": None,
                "headline": None,
                "title": None,
                "company_name": None,
                "company_linkedin_url": None,
                "location": None,
                "bio": None,
                "follower_count": None,
                "enrichment_status": "pending",
                "enriched_at": None,
                "times_seen": 1,
                "first_seen_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "exported": False,
                "exported_at": None,
            })
            engagement_links.append((contact_id, eng["activity_id"], author_url))

            # Index for future dedup within this batch
            if slug:
                by_slug[slug] = contact_id
            by_url[author_url] = contact_id

    # Write to DB
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Insert new contacts
            if new_contacts:
                from psycopg2.extras import execute_batch

                execute_batch(cur, """
                    INSERT INTO contacts (contact_id, slug, author_url,
                        enrichment_status, times_seen, first_seen_at, last_seen_at, exported)
                    VALUES (%(contact_id)s, %(slug)s, %(author_url)s,
                        %(enrichment_status)s, %(times_seen)s, %(first_seen_at)s, %(last_seen_at)s, %(exported)s)
                    ON CONFLICT (contact_id) DO NOTHING
                """, new_contacts)

            # Update existing contacts: times_seen + last_seen_at
            if updated_contact_ids:
                from psycopg2.extras import execute_batch

                execute_batch(cur, """
                    UPDATE contacts
                    SET times_seen = times_seen + 1, last_seen_at = %s
                    WHERE contact_id = %s
                """, [(now, cid) for cid in updated_contact_ids])

            # Link engagements to contacts
            if engagement_links:
                from psycopg2.extras import execute_batch

                execute_batch(cur, """
                    UPDATE engagements
                    SET contact_id = %s
                    WHERE activity_id = %s AND author_url = %s
                """, engagement_links)

        conn.commit()

    # Write tmp outputs
    save_json(os.path.join(TMP_DIR, "new_contacts.json"), new_contacts)
    save_json(
        os.path.join(TMP_DIR, "updated_contacts.json"),
        [{"contact_id": cid} for cid in updated_contact_ids],
    )

    print(f"\nNew contacts: {len(new_contacts)}")
    print(f"Updated contacts: {len(updated_contact_ids)}")
    with_slug = sum(1 for c in new_contacts if c["slug"])
    without_slug = sum(1 for c in new_contacts if not c["slug"])
    print(f"  {with_slug} with slug (commenters), {without_slug} without slug (likers)")
    print("Updated contacts and engagements in DB.")


if __name__ == "__main__":
    main()
