#!/usr/bin/env python3
"""
Instantly Analytics - Inbox Status Report

Reads raw data and produces per-domain inbox status:
- total_accounts, active, paused, errored
- daily_send_volume (recent), daily_limit capacity
- warmup_health_score
- inactive: true if zero sends in the lookback period

Usage:
    python .datagen/instantly-health-report/scripts/report_inbox_status.py [--days 30]
"""
import argparse
import json
import os
from collections import defaultdict


def load_json(path):
    """Load JSON file. Returns (data, error)."""
    if not os.path.exists(path):
        return None, f"File not found: {path}"
    try:
        with open(path) as f:
            return json.load(f), ""
    except Exception as e:
        return None, f"Failed to load {path}: {e}"


def extract_domain(email):
    return email.split("@")[-1] if "@" in email else "unknown"


def build_inbox_status(raw_dir, days):
    """Build inbox status report. Returns (report, error)."""
    accounts_data, err = load_json(os.path.join(raw_dir, "accounts.json"))
    if err:
        return None, err

    warmup_data, err = load_json(os.path.join(raw_dir, "warmup.json"))
    if err:
        warmup_data = []

    analytics_data, err = load_json(os.path.join(raw_dir, "account_analytics.json"))
    if err:
        analytics_data = []

    # Account status counts by domain
    domain_status = defaultdict(lambda: {"total": 0, "active": 0, "paused": 0, "errored": 0, "other": 0})
    domain_daily_limit = defaultdict(int)
    domain_warmup_scores = defaultdict(list)
    domain_warmup_active = defaultdict(int)
    for acct in accounts_data:
        email = acct.get("email", "")
        domain = extract_domain(email)
        domain_status[domain]["total"] += 1

        status = str(acct.get("status", "")).lower()
        if status in ("active", "1"):
            domain_status[domain]["active"] += 1
        elif status in ("paused", "2"):
            domain_status[domain]["paused"] += 1
        elif status in ("error", "errored", "3", "disabled"):
            domain_status[domain]["errored"] += 1
        else:
            domain_status[domain]["other"] += 1

        daily_limit = acct.get("daily_limit", 0) or acct.get("sending_limit", 0) or 0
        domain_daily_limit[domain] += daily_limit

        warmup_score = acct.get("stat_warmup_score")
        if warmup_score is not None:
            domain_warmup_scores[domain].append(float(warmup_score))

        warmup_st = acct.get("warmup_status")
        if warmup_st in (1, "1", "active"):
            domain_warmup_active[domain] += 1

    # Daily send volume by domain
    domain_daily_sent = defaultdict(list)
    for row in analytics_data:
        email = row.get("email_account", "")
        domain = extract_domain(email)
        sent = row.get("sent", 0)
        domain_daily_sent[domain].append(sent)

    # Warmup health by domain (from warmup API)
    domain_warmup_api = {}
    for record in warmup_data:
        email = record.get("email", "")
        domain = extract_domain(email)
        health = record.get("health_score") or record.get("warmup_health_score")
        if health is not None:
            if domain not in domain_warmup_api:
                domain_warmup_api[domain] = []
            domain_warmup_api[domain].append(float(health))

    # Build results
    all_domains = sorted(
        set(list(domain_status.keys()) + list(domain_warmup_api.keys()))
    )

    status_label_inactive = f"inactive_{days}d"

    results = []
    total_active_accts = 0
    total_errored_accts = 0
    status_counts = defaultdict(int)
    for domain in all_domains:
        st = domain_status.get(domain, {"total": 0, "active": 0, "paused": 0, "errored": 0, "other": 0})
        daily_sents = domain_daily_sent.get(domain, [])
        total_sent = sum(daily_sents)
        avg_daily = round(total_sent / max(len(daily_sents), 1), 1) if daily_sents else 0

        acct_warmup = domain_warmup_scores.get(domain, [])
        api_warmup = domain_warmup_api.get(domain, [])
        health_scores = acct_warmup if acct_warmup else api_warmup
        avg_health = round(sum(health_scores) / len(health_scores), 1) if health_scores else None

        total_active_accts += st["active"]
        total_errored_accts += st["errored"]

        warmup_count = domain_warmup_active.get(domain, 0)

        # Classify domain status
        if total_sent > 0:
            domain_flag = "sending"
        elif warmup_count > 0:
            domain_flag = "active_warmup"
        else:
            domain_flag = status_label_inactive
        status_counts[domain_flag] += 1

        results.append(
            {
                "domain": domain,
                "status": domain_flag,
                "total_accounts": st["total"],
                "active": st["active"],
                "paused": st["paused"],
                "errored": st["errored"],
                "warmup_active_accounts": warmup_count,
                "daily_send_volume": avg_daily,
                "total_sent_period": total_sent,
                "daily_limit_capacity": domain_daily_limit.get(domain, 0),
                "warmup_health_score": avg_health,
            }
        )

    results.sort(key=lambda x: x["total_accounts"], reverse=True)

    report = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "period_days": days,
        "totals": {
            "domains": len(results),
            "total_accounts": sum(r["total_accounts"] for r in results),
            "active_accounts": total_active_accts,
            "errored_accounts": total_errored_accts,
            "by_status": dict(status_counts),
        },
        "domains": results,
    }

    return report, ""


def main():
    parser = argparse.ArgumentParser(description="Instantly Analytics - Inbox Status Report")
    parser.add_argument("--raw-dir", default="./tmp/instantly-analytics/raw", help="Raw data directory")
    parser.add_argument("--out-dir", default="./tmp/instantly-analytics", help="Output directory")
    parser.add_argument("--days", type=int, default=30, help="Lookback period label (default: 30)")
    args = parser.parse_args()

    print("Generating inbox status report...", end="", flush=True)
    report, err = build_inbox_status(args.raw_dir, args.days)
    if err:
        print(f" FAILED: {err}")
        return

    out_path = os.path.join(args.out_dir, "inbox_status.json")
    os.makedirs(args.out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    totals = report["totals"]
    by_status = totals["by_status"]
    print(f" done")
    print(f"  {totals['domains']} domains, {totals['total_accounts']} accounts ({totals['active_accounts']} active, {totals['errored_accounts']} errored)")
    parts = [f"{v} {k}" for k, v in sorted(by_status.items())]
    print(f"  Domain status: {', '.join(parts)}")
    print(f"  Saved to: {out_path}")


if __name__ == "__main__":
    main()
