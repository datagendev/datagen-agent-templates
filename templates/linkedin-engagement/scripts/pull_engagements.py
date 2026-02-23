"""
Script 2: pull_engagements.py

READ    posts WHERE comments_pulled = false OR reactions_pulled = false
CALL    get_linkedin_person_post_comments(activity_id) for each post
CALL    get_linkedin_person_post_reactions(activity_id) for each post
WRITE   tmp/engagements.json
INSERT  engagements (append new, skip duplicates)
UPDATE  posts (mark pulled)
"""

import os
from datetime import datetime, timezone

from datagen_sdk import DatagenClient

from db import TMP_DIR, execute, execute_many, query, save_json

# Limit how many posts to process per run (controls API cost)
MAX_POSTS_PER_RUN = int(os.environ.get("MAX_POSTS", "2"))


def get_unpulled_posts():
    return query("""
        SELECT activity_id, profile_url, comments_count, reactions_count
        FROM posts
        WHERE comments_pulled = false OR reactions_pulled = false
        ORDER BY comments_count + reactions_count ASC
        LIMIT %s
    """, (MAX_POSTS_PER_RUN,))


def fetch_comments(client, activity_id):
    result = client.execute_tool(
        "get_linkedin_person_post_comments",
        {"activity_id": activity_id},
    )
    if not result or "comments" not in result:
        print(f"    WARNING: no comments returned for {activity_id}")
        return []
    return result["comments"]


def fetch_reactions(client, activity_id):
    result = client.execute_tool(
        "get_linkedin_person_post_reactions",
        {"activity_id": activity_id},
    )
    if not result or "reactions" not in result:
        print(f"    WARNING: no reactions returned for {activity_id}")
        return []
    return result["reactions"]


def extract_engagements(comments, reactions, activity_id):
    """Normalize comments and reactions into engagement records."""
    engagements = []
    seen = set()
    now = datetime.now(timezone.utc).isoformat()

    for c in comments:
        author = c.get("author", {})
        author_url = author.get("authorUrl", "")
        if not author_url:
            continue
        key = f"{activity_id}|{author_url}"
        if key in seen:
            continue
        seen.add(key)
        engagements.append({
            "activity_id": activity_id,
            "author_url": author_url,
            "engagement_type": "commented",
            "author_name": author.get("authorName", ""),
            "slug": author.get("authorPublicIdentifier"),
            "discovered_at": now,
            "contact_id": None,
        })

    for r in reactions:
        author = r.get("author", {})
        author_url = author.get("authorUrl", "")
        if not author_url:
            continue
        key = f"{activity_id}|{author_url}"
        if key in seen:
            continue
        seen.add(key)
        engagements.append({
            "activity_id": activity_id,
            "author_url": author_url,
            "engagement_type": "liked",
            "author_name": author.get("authorName", ""),
            "slug": None,  # Reactions don't provide slug
            "discovered_at": now,
            "contact_id": None,
        })

    return engagements


def main():
    unpulled = get_unpulled_posts()
    if not unpulled:
        print("No posts need engagement pulling.")
        save_json(os.path.join(TMP_DIR, "engagements.json"), [])
        return

    print(f"Processing {len(unpulled)} unpulled posts (MAX_POSTS={MAX_POSTS_PER_RUN})...")

    client = DatagenClient(timeout=120)
    now = datetime.now(timezone.utc)
    all_new = []

    for post in unpulled:
        aid = post["activity_id"]
        print(f"\n  Post {aid} ({post['comments_count']} comments, {post['reactions_count']} reactions)")

        comments = fetch_comments(client, aid)
        print(f"    Fetched {len(comments)} comments")

        reactions = fetch_reactions(client, aid)
        print(f"    Fetched {len(reactions)} reactions")

        engagements = extract_engagements(comments, reactions, aid)
        all_new.extend(engagements)

        # Mark post as pulled
        execute("""
            UPDATE posts
            SET comments_pulled = true, reactions_pulled = true, last_pulled_at = %s
            WHERE activity_id = %s
        """, (now, aid))

    # Insert engagements (skip duplicates via ON CONFLICT)
    if all_new:
        execute_many("""
            INSERT INTO engagements (activity_id, author_url, engagement_type,
                                     author_name, slug, discovered_at, contact_id)
            VALUES (%(activity_id)s, %(author_url)s, %(engagement_type)s,
                    %(author_name)s, %(slug)s, %(discovered_at)s, %(contact_id)s)
            ON CONFLICT (activity_id, author_url) DO NOTHING
        """, all_new)

    # Write tmp output
    save_json(os.path.join(TMP_DIR, "engagements.json"), all_new)
    print(f"\nWrote {len(all_new)} new engagements to tmp/engagements.json")

    commented = sum(1 for e in all_new if e["engagement_type"] == "commented")
    liked = sum(1 for e in all_new if e["engagement_type"] == "liked")
    print(f"  {commented} commenters (have slug), {liked} likers (need resolve)")
    print("Updated engagements and posts in DB.")


if __name__ == "__main__":
    main()
