"""
Preflight check: verify all prerequisites before running the pipeline.
Run this first. Exits non-zero if anything is missing.
"""

import os
import sys


def check(name, ok, fix=""):
    status = "OK" if ok else "MISSING"
    print(f"  [{status}] {name}")
    if not ok and fix:
        print(f"         -> {fix}")
    return ok


def main():
    print("Preflight checks\n")
    all_ok = True

    # 1. Python packages
    print("1. Python packages:")
    for pkg, import_name in [
        ("datagen-python-sdk", "datagen_sdk"),
        ("psycopg2-binary", "psycopg2"),
    ]:
        try:
            __import__(import_name)
            ok = True
        except ImportError:
            ok = False
        all_ok &= check(pkg, ok, f"pip install {pkg}")

    # 2. Environment variables
    print("\n2. Environment:")
    api_key = os.environ.get("DATAGEN_API_KEY")
    all_ok &= check(
        "DATAGEN_API_KEY",
        bool(api_key),
        "export DATAGEN_API_KEY=<your key> (get from app.datagen.dev)",
    )

    db_url = os.environ.get("DATABASE_URL")
    all_ok &= check(
        "DATABASE_URL",
        bool(db_url),
        "export DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require",
    )

    # 3. Database connection + tables
    print("\n3. Database:")
    if db_url:
        try:
            import psycopg2

            conn = psycopg2.connect(db_url, connect_timeout=10)
            check("connection", True)
            cur = conn.cursor()

            tables = [
                "monitored_profiles",
                "posts",
                "engagements",
                "contacts",
                "companies",
            ]
            for table in tables:
                cur.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                    (table,),
                )
                exists = cur.fetchone()[0]
                all_ok &= check(
                    f"table: {table}",
                    exists,
                    "Create table -- see context/data-model.md for schema",
                )

            cur.execute(
                "SELECT COUNT(*) FROM monitored_profiles WHERE status = 'active'"
            )
            profile_count = cur.fetchone()[0]
            check(
                f"active profiles: {profile_count}",
                profile_count > 0,
                "Add a profile to start monitoring",
            )

            conn.close()
        except Exception as e:
            all_ok &= check("connection", False, str(e))
    else:
        all_ok &= check("connection", False, "No DATABASE_URL available")

    # 4. DataGen API connectivity
    print("\n4. DataGen API:")
    if api_key:
        try:
            from datagen_sdk import DatagenClient

            client = DatagenClient()
            client.execute_tool("searchTools", {"query": "linkedin"})
            check("API reachable", True)
        except Exception as e:
            all_ok &= check("API reachable", False, str(e))
    else:
        all_ok &= check("API reachable", False, "Set DATAGEN_API_KEY first")

    # 5. Built-in DataGen tools (included with API key, no extra setup)
    print("\n5. Built-in DataGen tools:")
    builtin_tools = [
        "get_linkedin_person_posts",
        "get_linkedin_person_post_comments",
        "get_linkedin_person_post_reactions",
        "get_linkedin_person_data",
    ]
    print("  These are built-in DataGen tools (available with your API key):")
    for t in builtin_tools:
        print(f"    - {t}")

    # 6. External MCP servers (must be connected at app.datagen.dev/tools)
    print("\n6. External MCP servers:")
    print("  Connect these at https://app.datagen.dev/tools:")
    print("    - Neon (required): serverless Postgres for storage")
    print("    - Linkup (optional): web search fallback")

    # Summary
    print(
        f"\n{'All checks passed. Ready to run.' if all_ok else 'Some checks failed. Fix the issues above before running.'}"
    )
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
