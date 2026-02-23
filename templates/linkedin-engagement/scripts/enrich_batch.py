"""
Script 4: enrich_batch.py

Two-tier enrichment:
  1. Contacts WITH slug (commenters) -> Speaker CLI (free, 756M profiles)
  2. Contacts WITHOUT slug (likers)  -> get_linkedin_person_data (paid, resolves opaque URLs)

READ    contacts WHERE enrichment_status = 'pending'
            OR (enrichment_status = 'enriched' AND enriched_at < 30 days ago)
WRITE   tmp/enriched_contacts.json, tmp/companies.json
UPDATE  contacts, companies
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone

from datagen_sdk import DatagenClient

from db import TMP_DIR, execute, get_conn, query, save_json

MAX_ENRICH = int(os.environ.get("MAX_ENRICH", "3"))
REENRICH_DAYS = 30


def speaker_available():
    """Check if Speaker CLI is installed and authenticated."""
    try:
        result = subprocess.run(
            ["speaker", "count"], capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_enrichable_contacts():
    return query("""
        SELECT contact_id, slug, author_url, enrichment_status, enriched_at
        FROM contacts
        WHERE enrichment_status = 'pending'
           OR (enrichment_status = 'enriched'
               AND enriched_at < NOW() - INTERVAL '%s days')
        ORDER BY
            CASE WHEN slug IS NOT NULL THEN 0 ELSE 1 END,
            enriched_at NULLS FIRST
        LIMIT %s
    """ % (REENRICH_DAYS, MAX_ENRICH))


def get_existing_company_urls():
    rows = query("SELECT company_linkedin_url FROM companies", as_dict=False)
    return {r[0] for r in rows}


# --- Speaker enrichment (free, for contacts with slugs) ---

def enrich_via_speaker(slugs):
    """Batch-enrich contacts using Speaker CLI. Returns dict of slug -> person data."""
    if not slugs:
        return {}

    slug_list = "', '".join(slugs)
    sql = (
        f"SELECT slug, first, last, headline, loc, email, bio, "
        f"roles[1].title as title, roles[1].org as company, "
        f"roles[1].web as domain, roles[1].slug as company_slug "
        f"FROM people WHERE slug IN ('{slug_list}')"
    )

    result = subprocess.run(
        ["speaker", "query", sql],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"    Speaker error: {result.stderr.strip()}")
        return {}

    results = {}
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            person = json.loads(line)
            if person.get("slug"):
                results[person["slug"]] = person
        except json.JSONDecodeError:
            continue
    return results


def map_speaker_to_enriched(contact, person):
    """Map Speaker response fields to our contact schema."""
    company_slug = person.get("company_slug")
    company_url = f"https://www.linkedin.com/company/{company_slug}/" if company_slug else None

    return {
        "contact_id": contact["contact_id"],
        "slug": person.get("slug") or contact.get("slug"),
        "first_name": person.get("first"),
        "last_name": person.get("last"),
        "headline": person.get("headline"),
        "title": person.get("title"),
        "company_name": person.get("company"),
        "company_linkedin_url": company_url,
        "location": person.get("loc"),
        "bio": person.get("bio"),
        "follower_count": None,  # Speaker doesn't have this
        "enrichment_status": "enriched",
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "enriched_via": "speaker",
    }, company_url


# --- DataGen API enrichment (paid, for contacts without slugs) ---

def enrich_via_api(client, contact):
    """Call get_linkedin_person_data. Works for both slug URLs and opaque URLs."""
    url = (
        f"https://www.linkedin.com/in/{contact['slug']}"
        if contact.get("slug")
        else contact["author_url"]
    )
    result = client.execute_tool(
        "get_linkedin_person_data",
        {"linkedin_url": url},
    )
    if not result or "person" not in result:
        return None, None

    person = result["person"]
    positions = person.get("positions", {}).get("positionHistory", [])
    current = positions[0] if positions else {}

    enriched = {
        "contact_id": contact["contact_id"],
        "slug": person.get("publicIdentifier") or contact.get("slug"),
        "first_name": person.get("firstName"),
        "last_name": person.get("lastName"),
        "headline": person.get("headline"),
        "title": current.get("title"),
        "company_name": current.get("companyName"),
        "company_linkedin_url": current.get("linkedInUrl"),
        "location": person.get("location"),
        "bio": person.get("summary"),
        "follower_count": person.get("followerCount"),
        "enrichment_status": "enriched",
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "enriched_via": "api",
    }
    return enriched, current.get("linkedInUrl")


# --- Main ---

def main():
    enrichable = get_enrichable_contacts()
    if not enrichable:
        print("No contacts need enrichment.")
        save_json(os.path.join(TMP_DIR, "enriched_contacts.json"), [])
        save_json(os.path.join(TMP_DIR, "companies.json"), [])
        return

    use_speaker = speaker_available()
    company_urls = get_existing_company_urls()
    enriched_list = []
    new_companies = []
    failed = 0

    if use_speaker:
        with_slug = [c for c in enrichable if c.get("slug")]
        without_slug = [c for c in enrichable if not c.get("slug")]
        print(f"Enriching {len(enrichable)} contacts (MAX_ENRICH={MAX_ENRICH})...")
        print(f"  {len(with_slug)} via Speaker (free), {len(without_slug)} via API (paid)")
    else:
        with_slug = []
        without_slug = enrichable
        print(f"Enriching {len(enrichable)} contacts via API (Speaker not available)...")

    # --- Tier 1: Speaker batch for contacts with slugs ---
    if with_slug:
        slugs = [c["slug"] for c in with_slug]
        print(f"\n[Speaker] Querying {len(slugs)} slugs...")
        speaker_results = enrich_via_speaker(slugs)
        print(f"[Speaker] Got {len(speaker_results)} results")

        speaker_misses = []
        for contact in with_slug:
            slug = contact["slug"]
            person = speaker_results.get(slug)
            if person:
                enriched, company_url = map_speaker_to_enriched(contact, person)
                enriched_list.append(enriched)
                print(
                    f"  [Speaker] {slug} -> {enriched['first_name']} {enriched['last_name']}, "
                    f"{enriched['title']} @ {enriched['company_name']}"
                )

                if company_url and company_url not in company_urls:
                    new_companies.append({
                        "company_linkedin_url": company_url,
                        "name": enriched["company_name"],
                        "enrichment_status": "pending",
                    })
                    company_urls.add(company_url)
            else:
                # Speaker miss -- fall back to API
                speaker_misses.append(contact)
                print(f"  [Speaker] {slug} -> not found, will try API")

        # Add Speaker misses to API queue
        without_slug.extend(speaker_misses)

    # --- Tier 2: API for remaining contacts ---
    if without_slug:
        print(f"\n[API] Enriching {len(without_slug)} contacts...")
        client = DatagenClient(timeout=60)

        for i, contact in enumerate(without_slug):
            slug_or_url = contact.get("slug") or contact["author_url"]
            print(f"  [API] [{i+1}/{len(without_slug)}] {slug_or_url}...", end=" ")

            try:
                enriched, company_url = enrich_via_api(client, contact)
                if enriched:
                    enriched_list.append(enriched)
                    print(
                        f"-> {enriched['first_name']} {enriched['last_name']}, "
                        f"{enriched['title']} @ {enriched['company_name']}"
                    )

                    if company_url and company_url not in company_urls:
                        new_companies.append({
                            "company_linkedin_url": company_url,
                            "name": enriched["company_name"],
                            "enrichment_status": "pending",
                        })
                        company_urls.add(company_url)
                else:
                    failed += 1
                    print("FAILED (no data)")
                    execute("""
                        UPDATE contacts SET enrichment_status = 'failed'
                        WHERE contact_id = %s
                    """, (contact["contact_id"],))
            except Exception as e:
                failed += 1
                print(f"FAILED ({e})")
                execute("""
                    UPDATE contacts SET enrichment_status = 'failed'
                    WHERE contact_id = %s
                """, (contact["contact_id"],))

            if i < len(without_slug) - 1:
                time.sleep(0.5)

    # --- Write to DB ---

    # Insert companies FIRST (contacts have FK to companies)
    if new_companies:
        from psycopg2.extras import execute_batch

        with get_conn() as conn:
            with conn.cursor() as cur:
                execute_batch(cur, """
                    INSERT INTO companies (company_linkedin_url, name, enrichment_status)
                    VALUES (%(company_linkedin_url)s, %(name)s, %(enrichment_status)s)
                    ON CONFLICT (company_linkedin_url) DO NOTHING
                """, new_companies)
            conn.commit()

    # Then update contacts
    if enriched_list:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for e in enriched_list:
                    cur.execute("""
                        UPDATE contacts
                        SET slug = %s, first_name = %s, last_name = %s,
                            headline = %s, title = %s, company_name = %s,
                            company_linkedin_url = %s, location = %s,
                            bio = %s, follower_count = %s,
                            enrichment_status = %s, enriched_at = %s
                        WHERE contact_id = %s
                    """, (
                        e["slug"], e["first_name"], e["last_name"],
                        e["headline"], e["title"], e["company_name"],
                        e["company_linkedin_url"], e["location"],
                        e["bio"], e["follower_count"],
                        e["enrichment_status"], e["enriched_at"],
                        e["contact_id"],
                    ))
            conn.commit()

    # Write tmp outputs
    save_json(os.path.join(TMP_DIR, "enriched_contacts.json"), enriched_list)
    save_json(os.path.join(TMP_DIR, "companies.json"), new_companies)

    speaker_count = sum(1 for e in enriched_list if e.get("enriched_via") == "speaker")
    api_count = sum(1 for e in enriched_list if e.get("enriched_via") == "api")
    print(f"\nEnriched: {len(enriched_list)} (Speaker: {speaker_count}, API: {api_count}), Failed: {failed}")
    print(f"New companies discovered: {len(new_companies)}")
    print("Updated contacts and companies in DB.")


if __name__ == "__main__":
    main()
