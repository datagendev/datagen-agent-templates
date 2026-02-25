#!/usr/bin/env python3
"""
Instantly Analytics - Domain Health Report

Reads raw data and produces per-domain health metrics:
- sent, bounced, bounce_rate
- replies, reply_rate
- warmup_health_score, inbox_placement_rate
- account_count, active_count

Usage:
    python .datagen/instantly-health-report/scripts/report_domain_health.py [--raw-dir ...] [--out-dir ...]
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta


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
    """Extract domain from email address."""
    return email.split("@")[-1] if "@" in email else "unknown"


def build_domain_health(raw_dir, days):
    """Build domain health report from raw data. Returns (report, error)."""
    # Load raw data
    analytics, err = load_json(os.path.join(raw_dir, "account_analytics.json"))
    if err:
        return None, err

    replies_data, err = load_json(os.path.join(raw_dir, "replies.json"))
    if err:
        replies_data = []

    # Filter replies to the lookback window
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    replies_data = [r for r in replies_data if (r.get("timestamp_created") or "") >= cutoff]

    warmup_data, err = load_json(os.path.join(raw_dir, "warmup.json"))
    if err:
        warmup_data = []

    accounts_data, err = load_json(os.path.join(raw_dir, "accounts.json"))
    if err:
        accounts_data = []

    # Aggregate sent/bounced by domain from account analytics
    domain_sent = defaultdict(int)
    domain_bounced = defaultdict(int)
    for row in analytics:
        email = row.get("email_account", "")
        domain = extract_domain(email)
        domain_sent[domain] += row.get("sent", 0)
        domain_bounced[domain] += row.get("bounced", 0)

    # Count replies by domain (from receiving email account)
    domain_replies = defaultdict(int)
    for email in replies_data:
        campaign_id = email.get("campaign_id")
        if not campaign_id:
            continue
        eaccount = email.get("eaccount", "")
        domain = extract_domain(eaccount)
        domain_replies[domain] += 1

    # Warmup health by domain
    domain_warmup = {}
    for record in warmup_data:
        email = record.get("email", "")
        domain = extract_domain(email)
        health = record.get("health_score") or record.get("warmup_health_score")
        placement = record.get("inbox_placement_rate") or record.get("inbox_rate")
        if domain not in domain_warmup:
            domain_warmup[domain] = {"health_scores": [], "placement_rates": []}
        if health is not None:
            domain_warmup[domain]["health_scores"].append(float(health))
        if placement is not None:
            domain_warmup[domain]["placement_rates"].append(float(placement))

    # Account counts by domain (from /accounts endpoint)
    domain_account_total = defaultdict(int)
    domain_account_active = defaultdict(int)
    for acct in accounts_data:
        email = acct.get("email", "")
        domain = extract_domain(email)
        domain_account_total[domain] += 1
        status = acct.get("status", "")
        if status in ("active", 1, "1"):
            domain_account_active[domain] += 1

    # Also count unique accounts from analytics for domains not in /accounts
    # (accounts may have been removed but still have historical send data)
    domain_analytics_accounts = defaultdict(set)
    for row in analytics:
        email = row.get("email_account", "")
        if email:
            domain = extract_domain(email)
            domain_analytics_accounts[domain].add(email)

    for domain, emails in domain_analytics_accounts.items():
        if domain not in domain_account_total or domain_account_total[domain] == 0:
            domain_account_total[domain] = len(emails)
            # Mark as active since they have recent send data
            domain_account_active[domain] = len(emails)

    # Merge all domains
    all_domains = sorted(
        set(
            list(domain_sent.keys())
            + list(domain_replies.keys())
            + list(domain_warmup.keys())
            + list(domain_account_total.keys())
        )
    )

    results = []
    for domain in all_domains:
        sent = domain_sent.get(domain, 0)
        bounced = domain_bounced.get(domain, 0)
        replies = domain_replies.get(domain, 0)

        warmup_info = domain_warmup.get(domain, {})
        health_scores = warmup_info.get("health_scores", [])
        placement_rates = warmup_info.get("placement_rates", [])

        results.append(
            {
                "domain": domain,
                "sent": sent,
                "bounced": bounced,
                "bounce_rate": round(bounced / sent * 100, 2) if sent > 0 else 0,
                "replies": replies,
                "reply_rate": round(replies / sent * 100, 2) if sent > 0 else 0,
                "warmup_health_score": round(sum(health_scores) / len(health_scores), 1) if health_scores else None,
                "inbox_placement_rate": round(sum(placement_rates) / len(placement_rates), 1) if placement_rates else None,
                "account_count": domain_account_total.get(domain, 0),
                "active_count": domain_account_active.get(domain, 0),
            }
        )

    # Sort by sent volume descending
    results.sort(key=lambda x: x["sent"], reverse=True)

    # Totals
    total_sent = sum(r["sent"] for r in results)
    total_bounced = sum(r["bounced"] for r in results)
    total_replies = sum(r["replies"] for r in results)

    report = {
        "generated_at": datetime.now().isoformat(),
        "period_days": days,
        "totals": {
            "domains": len(results),
            "total_sent": total_sent,
            "total_bounced": total_bounced,
            "total_replies": total_replies,
            "overall_reply_rate": round(total_replies / total_sent * 100, 2) if total_sent > 0 else 0,
            "overall_bounce_rate": round(total_bounced / total_sent * 100, 2) if total_sent > 0 else 0,
        },
        "domains": results,
    }

    return report, ""


def main():
    parser = argparse.ArgumentParser(description="Instantly Analytics - Domain Health Report")
    parser.add_argument("--raw-dir", default="./tmp/instantly-analytics/raw", help="Raw data directory")
    parser.add_argument("--out-dir", default="./tmp/instantly-analytics", help="Output directory")
    parser.add_argument("--days", type=int, default=30, help="Lookback period for reply filtering (default: 30)")
    args = parser.parse_args()

    print(f"Generating domain health report (last {args.days}d)...", end="", flush=True)
    report, err = build_domain_health(args.raw_dir, args.days)
    if err:
        print(f" FAILED: {err}")
        return

    out_path = os.path.join(args.out_dir, "domain_health.json")
    os.makedirs(args.out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    totals = report["totals"]
    print(f" done")
    print(f"  {totals['domains']} domains, {totals['total_sent']} sent, {totals['total_replies']} replies")
    print(f"  Overall reply rate: {totals['overall_reply_rate']}%, bounce rate: {totals['overall_bounce_rate']}%")
    print(f"  Saved to: {out_path}")


if __name__ == "__main__":
    main()
