#!/usr/bin/env python3
"""
Instantly Analytics - Raw Data Fetcher

Fetches all raw data from Instantly API v2 in one pass:
- GET /accounts (paginated) -> accounts.json
- GET /accounts/analytics/daily -> account_analytics.json
- GET /campaigns/analytics -> campaign_analytics.json
- GET /emails?email_type=received (paginated) -> replies.json
- POST /accounts/warmup-analytics (batched) -> warmup.json

Usage:
    python .datagen/instantly-health-report/scripts/fetch_data.py [--days 30] [--force]
"""
import argparse
import json
import os
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.instantly.ai/api/v2"


def get_headers():
    key = os.getenv("INSTANTLY_API_KEY")
    if not key:
        raise RuntimeError("INSTANTLY_API_KEY not found in .env")
    return {"Authorization": f"Bearer {key}"}


def api_get(path, params=None, timeout=60, max_retries=3):
    """GET with retry logic. Returns (data, error)."""
    headers = get_headers()
    for attempt in range(max_retries):
        try:
            resp = requests.get(
                f"{API_BASE}{path}",
                params=params or {},
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json(), ""
        except (requests.exceptions.HTTPError, requests.exceptions.Timeout) as e:
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            return None, f"GET {path} failed after {max_retries} retries: {e}"
        except Exception as e:
            return None, f"GET {path} unexpected error: {e}"


def api_post(path, json_body=None, timeout=60, max_retries=3):
    """POST with retry logic. Returns (data, error)."""
    headers = get_headers()
    headers["Content-Type"] = "application/json"
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{API_BASE}{path}",
                json=json_body or {},
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json(), ""
        except (requests.exceptions.HTTPError, requests.exceptions.Timeout) as e:
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            return None, f"POST {path} failed after {max_retries} retries: {e}"
        except Exception as e:
            return None, f"POST {path} unexpected error: {e}"


def paginate_get(path, params, item_key="items", cursor_key="next_starting_after"):
    """Paginate a GET endpoint. Returns (all_items, error)."""
    all_items = []
    cursor = None
    page = 0
    while True:
        p = {**params}
        if cursor:
            p["starting_after"] = cursor
        data, err = api_get(path, params=p, timeout=30)
        if err:
            if all_items:
                print(f"\n  WARN: pagination stopped at page {page}: {err}")
                return all_items, ""
            return [], err

        items = data.get(item_key, [])
        all_items.extend(items)
        cursor = data.get(cursor_key)
        page += 1
        if page % 10 == 0:
            print(f"    ...page {page}, {len(all_items)} items", flush=True)
        if not cursor or not items:
            break
    return all_items, ""


def save_json(data, path):
    """Save data as JSON."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def fetch_accounts(out_dir, force=False):
    """Fetch all email accounts. Returns (data, error)."""
    out_path = os.path.join(out_dir, "accounts.json")
    if not force and os.path.exists(out_path):
        print("  [cached]", flush=True)
        with open(out_path) as f:
            return json.load(f), ""

    items, err = paginate_get("/accounts", {"limit": 100})
    if err:
        return None, err
    save_json(items, out_path)
    return items, ""


def fetch_account_analytics(out_dir, start_date, end_date, force=False):
    """Fetch daily per-account sent/bounced. Returns (data, error)."""
    out_path = os.path.join(out_dir, "account_analytics.json")
    if not force and os.path.exists(out_path):
        print("  [cached]", flush=True)
        with open(out_path) as f:
            return json.load(f), ""

    data, err = api_get(
        "/accounts/analytics/daily",
        params={"start_date": start_date, "end_date": end_date},
    )
    if err:
        return None, err
    save_json(data, out_path)
    return data, ""


def fetch_campaign_analytics(out_dir, force=False):
    """Fetch per-campaign aggregate metrics. Returns (data, error)."""
    out_path = os.path.join(out_dir, "campaign_analytics.json")
    if not force and os.path.exists(out_path):
        print("  [cached]", flush=True)
        with open(out_path) as f:
            return json.load(f), ""

    data, err = api_get(
        "/campaigns/analytics",
        params={"exclude_total_leads_count": "true"},
    )
    if err:
        return None, err
    # API sometimes returns [[...]] wrapper
    if isinstance(data, list) and data and isinstance(data[0], list):
        data = data[0]
    save_json(data, out_path)
    return data, ""


def fetch_replies(out_dir, force=False):
    """Fetch received campaign emails for reply attribution. Returns (data, error)."""
    out_path = os.path.join(out_dir, "replies.json")
    if not force and os.path.exists(out_path):
        print("  [cached]", flush=True)
        with open(out_path) as f:
            return json.load(f), ""

    items, err = paginate_get(
        "/emails",
        {"email_type": "received", "mode": "emode_focused", "limit": 100, "preview_only": "true"},
    )
    if err:
        return None, err
    save_json(items, out_path)
    return items, ""


def fetch_warmup(out_dir, accounts, force=False):
    """Fetch warmup analytics per domain. Returns (data, error)."""
    out_path = os.path.join(out_dir, "warmup.json")
    if not force and os.path.exists(out_path):
        print("  [cached]", flush=True)
        with open(out_path) as f:
            return json.load(f), ""

    # Extract unique email addresses from accounts
    emails = []
    for acct in accounts:
        email = acct.get("email", "") if isinstance(acct, dict) else ""
        if email:
            emails.append(email)

    if not emails:
        save_json([], out_path)
        return [], ""

    # Batch by 50 emails per request
    all_warmup = []
    batch_size = 50
    for i in range(0, len(emails), batch_size):
        batch = emails[i : i + batch_size]
        data, err = api_post(
            "/accounts/warmup-analytics",
            json_body={"emails": batch},
        )
        if err:
            print(f"\n  WARN: warmup batch {i//batch_size + 1} failed: {err}")
            continue
        if isinstance(data, list):
            all_warmup.extend(data)
        elif isinstance(data, dict):
            all_warmup.append(data)

    save_json(all_warmup, out_path)
    return all_warmup, ""


def main():
    parser = argparse.ArgumentParser(description="Instantly Analytics - Fetch raw data")
    parser.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    parser.add_argument("--force", action="store_true", help="Refetch even if cached")
    parser.add_argument("--out-dir", default="./tmp/instantly-analytics/raw", help="Output directory")
    args = parser.parse_args()

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    os.makedirs(args.out_dir, exist_ok=True)

    errors = []

    # 1. Accounts
    print(f"[1/5] Fetching accounts...", end="", flush=True)
    accounts, err = fetch_accounts(args.out_dir, args.force)
    if err:
        errors.append(f"accounts: {err}")
        print(f" FAILED: {err}")
        accounts = []
    else:
        count = len(accounts)
        print(f" {count} accounts")

    # 2. Account analytics (daily)
    print(f"[2/5] Fetching account analytics ({start_date} to {end_date})...", end="", flush=True)
    analytics, err = fetch_account_analytics(args.out_dir, start_date, end_date, args.force)
    if err:
        errors.append(f"account_analytics: {err}")
        print(f" FAILED: {err}")
    else:
        print(f" {len(analytics)} rows")

    # 3. Campaign analytics
    print(f"[3/5] Fetching campaign analytics...", end="", flush=True)
    campaigns, err = fetch_campaign_analytics(args.out_dir, args.force)
    if err:
        errors.append(f"campaign_analytics: {err}")
        print(f" FAILED: {err}")
    else:
        print(f" {len(campaigns)} campaigns")

    # 4. Replies (paginated)
    print(f"[4/5] Fetching received emails for reply attribution...", flush=True)
    replies, err = fetch_replies(args.out_dir, args.force)
    if err:
        errors.append(f"replies: {err}")
        print(f"  FAILED: {err}")
    else:
        print(f"  {len(replies)} received emails")

    # 5. Warmup analytics
    print(f"[5/5] Fetching warmup analytics...", end="", flush=True)
    warmup, err = fetch_warmup(args.out_dir, accounts, args.force)
    if err:
        errors.append(f"warmup: {err}")
        print(f" FAILED: {err}")
    else:
        print(f" {len(warmup)} warmup records")

    # Summary
    print(f"\nRaw data saved to: {args.out_dir}/")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        # Save errors
        save_json(
            {"errors": errors, "timestamp": datetime.now().isoformat()},
            os.path.join(args.out_dir, "..", "errors.json"),
        )
    else:
        print("All fetches succeeded.")


if __name__ == "__main__":
    main()
