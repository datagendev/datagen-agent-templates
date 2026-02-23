"""
Base preflight checks shared across all agent templates.
Checks: DATAGEN_API_KEY, datagen-python-sdk, API connectivity.

Usage:
    Import and call run_base_checks() from your template's preflight.py.
    Returns True if all base checks pass, False otherwise.
"""

import os
import sys


def check(name, ok, fix=""):
    """Print a check result and return whether it passed."""
    status = "OK" if ok else "MISSING"
    print(f"  [{status}] {name}")
    if not ok and fix:
        print(f"         -> {fix}")
    return ok


def run_base_checks():
    """Run base DataGen checks. Returns True if all pass."""
    all_ok = True

    # 1. Python SDK
    print("1. DataGen SDK:")
    try:
        import datagen_sdk
        check(f"datagen-python-sdk ({datagen_sdk.__version__})", True)
    except ImportError:
        all_ok &= check("datagen-python-sdk", False, "pip install datagen-python-sdk")

    # 2. API key
    print("\n2. Environment:")
    api_key = os.environ.get("DATAGEN_API_KEY")
    all_ok &= check(
        "DATAGEN_API_KEY",
        bool(api_key),
        "export DATAGEN_API_KEY=<your key> (get from app.datagen.dev)",
    )

    # 3. API connectivity
    print("\n3. DataGen API:")
    if api_key:
        try:
            from datagen_sdk import DatagenClient

            client = DatagenClient()
            client.execute_tool("searchTools", {"query": "test"})
            check("API reachable", True)
        except Exception as e:
            all_ok &= check("API reachable", False, str(e))
    else:
        all_ok &= check("API reachable", False, "Set DATAGEN_API_KEY first")

    return all_ok


if __name__ == "__main__":
    print("DataGen base preflight checks\n")
    ok = run_base_checks()
    print(
        f"\n{'All base checks passed.' if ok else 'Some checks failed. Fix the issues above.'}"
    )
    sys.exit(0 if ok else 1)
