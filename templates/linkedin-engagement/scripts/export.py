"""
Script 5: export.py

READ    contacts WHERE enrichment_status = 'enriched' AND exported = false
DO      Push to destination (currently: write CSV for review)
WRITE   tmp/export_log.json, tmp/export.csv
UPDATE  contacts (mark exported)
"""

import csv
import os
from datetime import datetime, timezone

from db import TMP_DIR, execute_many, query, save_json


def main():
    exportable = query("""
        SELECT contact_id, slug, first_name, last_name, headline, title,
               company_name, location, bio, follower_count,
               times_seen, first_seen_at, last_seen_at, author_url
        FROM contacts
        WHERE enrichment_status = 'enriched' AND exported = false
    """)

    if not exportable:
        print("No contacts to export.")
        save_json(os.path.join(TMP_DIR, "export_log.json"), [])
        return

    print(f"Exporting {len(exportable)} contacts...")
    now = datetime.now(timezone.utc).isoformat()

    # Write CSV
    csv_path = os.path.join(TMP_DIR, "export.csv")
    fields = [
        "slug", "first_name", "last_name", "headline", "title",
        "company_name", "location", "bio", "follower_count",
        "times_seen", "first_seen_at", "last_seen_at",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=fields + ["linkedin_url"], extrasaction="ignore"
        )
        writer.writeheader()
        for c in exportable:
            row = {k: c.get(k) for k in fields}
            row["linkedin_url"] = (
                f"https://www.linkedin.com/in/{c['slug']}"
                if c.get("slug")
                else c.get("author_url")
            )
            writer.writerow(row)

    print(f"Wrote {csv_path}")

    # Build export log
    export_log = []
    contact_ids = []
    for c in exportable:
        contact_ids.append({"contact_id": c["contact_id"], "exported_at": now})
        export_log.append({
            "contact_id": c["contact_id"],
            "slug": c.get("slug"),
            "name": f"{c.get('first_name', '') or ''} {c.get('last_name', '') or ''}".strip(),
            "exported_at": now,
        })

    # Mark as exported in DB
    execute_many("""
        UPDATE contacts
        SET exported = true, exported_at = %(exported_at)s
        WHERE contact_id = %(contact_id)s
    """, contact_ids)

    save_json(os.path.join(TMP_DIR, "export_log.json"), export_log)
    print(f"Wrote {len(export_log)} entries to tmp/export_log.json")
    print("Marked contacts as exported in DB.")


if __name__ == "__main__":
    main()
