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
    try:
        import datagen_sdk
        check(f"datagen-python-sdk ({datagen_sdk.__version__})", True)
    except ImportError:
        all_ok &= check("datagen-python-sdk", False, "pip install datagen-python-sdk")

    # 2. Environment variables
    print("\n2. Environment:")
    api_key = os.environ.get("DATAGEN_API_KEY")
    all_ok &= check(
        "DATAGEN_API_KEY",
        bool(api_key),
        "export DATAGEN_API_KEY=<your key> (get from app.datagen.dev)",
    )

    # 3. DataGen API connectivity
    print("\n3. DataGen API:")
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

    # 4. Database MCP (auto-detect Neon, Supabase, or other)
    print("\n4. Database MCP:")
    if api_key:
        try:
            from db import detect_db_tool
            db_tool = detect_db_tool()
            check(f"database tool: {db_tool}", True)

            # Test with a simple query
            from db import _run_sql
            _run_sql("SELECT 1")
            check("database connection", True)
        except RuntimeError as e:
            all_ok &= check(
                "database MCP",
                False,
                "Connect Neon or Supabase at https://app.datagen.dev/tools",
            )
        except Exception as e:
            all_ok &= check("database connection", False, str(e))
    else:
        all_ok &= check("database MCP", False, "Set DATAGEN_API_KEY first")

    # 5. Check tables exist
    print("\n5. Database tables:")
    if api_key:
        try:
            from db import query
            tables = [
                "monitored_profiles",
                "posts",
                "engagements",
                "contacts",
                "companies",
            ]
            for table in tables:
                result = query(
                    f"SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    f"WHERE table_name = '{table}')"
                )
                exists = False
                if result:
                    row = result[0]
                    exists = list(row.values())[0] if isinstance(row, dict) else row
                all_ok &= check(
                    f"table: {table}",
                    exists,
                    "Create table -- see context/data-model.md for schema",
                )

            # Check if any profiles are configured
            result = query(
                "SELECT COUNT(*) as cnt FROM monitored_profiles WHERE status = 'active'"
            )
            profile_count = 0
            if result:
                row = result[0]
                profile_count = row.get("cnt", 0) if isinstance(row, dict) else 0
            check(
                f"active profiles: {profile_count}",
                profile_count > 0,
                "Add a profile to start monitoring",
            )
        except Exception as e:
            all_ok &= check("table check", False, str(e))

    # 6. Built-in DataGen tools
    print("\n6. Built-in DataGen tools:")
    builtin_tools = [
        "get_linkedin_person_posts",
        "get_linkedin_person_post_comments",
        "get_linkedin_person_post_reactions",
        "get_linkedin_person_data",
    ]
    print("  These are built-in DataGen tools (available with your API key):")
    for t in builtin_tools:
        print(f"    - {t}")

    # Summary
    print(
        f"\n{'All checks passed. Ready to run.' if all_ok else 'Some checks failed. Fix the issues above before running.'}"
    )
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
