"""
Script 1: check_profiles.py

READ    monitored_profiles WHERE status = 'active' AND last_checked_at < today
CALL    get_linkedin_person_posts(linkedin_url) for each profile
WRITE   tmp/new_posts.json
UPDATE  monitored_profiles (last_checked_at, posts_backfilled)
INSERT  posts (new posts, skip duplicates)
"""

import os
from datetime import datetime, timezone

from datagen_sdk import DatagenClient

from db import TMP_DIR, execute, execute_many, query, save_json


def get_due_profiles():
    """Return active profiles that haven't been checked today."""
    return query("""
        SELECT linkedin_url, name, status, last_checked_at, posts_backfilled
        FROM monitored_profiles
        WHERE status = 'active'
          AND (last_checked_at IS NULL OR last_checked_at::date < CURRENT_DATE)
    """)


def fetch_posts(client, profile):
    """Fetch posts for a profile using DataGen tool."""
    result = client.execute_tool(
        "get_linkedin_person_posts",
        {"linkedin_url": profile["linkedin_url"]},
    )
    if not result or "posts" not in result:
        print(f"  WARNING: no posts returned for {profile['name']}")
        return []
    return result["posts"]


def get_existing_activity_ids():
    rows = query("SELECT activity_id FROM posts", as_dict=False)
    return {r[0] for r in rows}


def filter_new_posts(api_posts, profile, existing_ids):
    """Filter posts based on backfill status and existing data."""
    new_posts = []
    for post in api_posts:
        aid = post.get("activityId")
        if not aid or aid in existing_ids:
            continue

        posted_at = post.get("activityDate")

        # If already backfilled, only take posts newer than last check
        if profile["posts_backfilled"] and profile["last_checked_at"]:
            if posted_at and posted_at < profile["last_checked_at"].isoformat():
                continue

        new_posts.append({
            "activity_id": aid,
            "profile_url": profile["linkedin_url"],
            "posted_at": posted_at,
            "reactions_count": post.get("reactionsCount", 0),
            "comments_count": post.get("commentsCount", 0),
            "comments_pulled": False,
            "reactions_pulled": False,
            "last_pulled_at": None,
        })

    return new_posts


def main():
    due = get_due_profiles()
    if not due:
        print("No profiles due for checking.")
        save_json(os.path.join(TMP_DIR, "new_posts.json"), [])
        return

    existing_ids = get_existing_activity_ids()
    print(f"Checking {len(due)} profile(s)...")
    client = DatagenClient()
    now = datetime.now(timezone.utc)

    all_new_posts = []

    for profile in due:
        print(f"  Fetching posts for {profile['name']}...")
        api_posts = fetch_posts(client, profile)
        print(f"    Got {len(api_posts)} posts from API")

        new_posts = filter_new_posts(api_posts, profile, existing_ids)
        print(f"    {len(new_posts)} are new")

        all_new_posts.extend(new_posts)

        # Update profile state
        execute("""
            UPDATE monitored_profiles
            SET last_checked_at = %s, posts_backfilled = true
            WHERE linkedin_url = %s
        """, (now, profile["linkedin_url"]))

        # Track new IDs to avoid dupes within this run
        for p in new_posts:
            existing_ids.add(p["activity_id"])

    # Insert new posts
    if all_new_posts:
        execute_many("""
            INSERT INTO posts (activity_id, profile_url, posted_at,
                               reactions_count, comments_count,
                               comments_pulled, reactions_pulled, last_pulled_at)
            VALUES (%(activity_id)s, %(profile_url)s, %(posted_at)s,
                    %(reactions_count)s, %(comments_count)s,
                    %(comments_pulled)s, %(reactions_pulled)s, %(last_pulled_at)s)
            ON CONFLICT (activity_id) DO NOTHING
        """, all_new_posts)

    # Write tmp output for agent review
    save_json(os.path.join(TMP_DIR, "new_posts.json"), all_new_posts)
    print(f"\nWrote {len(all_new_posts)} new posts to tmp/new_posts.json")
    print("Updated monitored_profiles and posts in DB.")


if __name__ == "__main__":
    main()
