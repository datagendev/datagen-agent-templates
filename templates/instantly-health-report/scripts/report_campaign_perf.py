#!/usr/bin/env python3
"""
Instantly Analytics - Campaign Performance Report

Reads raw data and produces per-campaign performance metrics:
- sent, contacted, replied, reply_rate
- unique_replies, automatic_replies
- opportunities, opportunity_value, opportunity_rate
- reply_sentiment breakdown (from ai_interest_value)
- top replying domains per campaign

Usage:
    python .datagen/instantly-health-report/scripts/report_campaign_perf.py [--raw-dir ...] [--out-dir ...]
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
    return email.split("@")[-1] if "@" in email else "unknown"


def classify_interest(value):
    """Classify ai_interest_value into sentiment bucket."""
    if not value:
        return "unknown"
    v = str(value).lower()
    if v in ("positive", "interested", "1", "true"):
        return "positive"
    if v in ("negative", "not_interested", "not interested", "-1", "false"):
        return "negative"
    if v in ("neutral", "maybe", "0"):
        return "neutral"
    return "unknown"


def build_campaign_performance(raw_dir, days):
    """Build campaign performance report. Returns (report, error)."""
    campaigns, err = load_json(os.path.join(raw_dir, "campaign_analytics.json"))
    if err:
        return None, err

    replies_data, err = load_json(os.path.join(raw_dir, "replies.json"))
    if err:
        replies_data = []

    # Filter replies to the lookback window
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    replies_data = [r for r in replies_data if (r.get("timestamp_created") or "") >= cutoff]

    # Build reply data per campaign: domains, sentiment
    campaign_reply_domains = defaultdict(lambda: defaultdict(int))
    campaign_reply_sentiment = defaultdict(lambda: defaultdict(int))
    campaign_reply_count = defaultdict(int)
    for email in replies_data:
        cid = email.get("campaign_id")
        if not cid:
            continue
        eaccount = email.get("eaccount", "")
        domain = extract_domain(eaccount)
        campaign_reply_domains[cid][domain] += 1
        campaign_reply_count[cid] += 1

        interest = email.get("ai_interest_value", "")
        sentiment = classify_interest(interest)
        campaign_reply_sentiment[cid][sentiment] += 1

    # Build campaign results
    results = []
    for c in campaigns:
        cid = c.get("campaign_id", "")
        sent = c.get("emails_sent_count", 0)
        contacted = c.get("leads_contacted_count", c.get("contacted", 0))
        # Use email-attributed reply count (from replies.json, date-filtered)
        # instead of campaign API reply_count which is all-time and undercounts threads
        replied = campaign_reply_count.get(cid, 0)
        unique_replies = c.get("unique_reply_count", c.get("replies_unique", 0))
        bounced = c.get("bounced_count", c.get("bounces", 0))
        opps = c.get("total_opportunities", c.get("opportunities", 0))
        opp_value = c.get("opportunity_value", 0)

        # Top replying domains for this campaign (from email data)
        domain_counts = campaign_reply_domains.get(cid, {})
        top_domains = sorted(domain_counts.items(), key=lambda x: -x[1])[:5]

        # Sentiment breakdown
        sentiment = dict(campaign_reply_sentiment.get(cid, {}))

        results.append(
            {
                "campaign_id": cid,
                "campaign_name": c.get("campaign_name", c.get("name", "Unknown")),
                "status": c.get("campaign_status", c.get("status", "")),
                "sent": sent,
                "contacted": contacted,
                "replied": replied,
                "reply_rate": round(replied / sent * 100, 2) if sent > 0 else 0,
                "unique_replies": unique_replies,
                "bounced": bounced,
                "bounce_rate": round(bounced / sent * 100, 2) if sent > 0 else 0,
                "opportunities": opps,
                "opportunity_value": opp_value,
                "opportunity_rate": round(opps / sent * 100, 2) if sent > 0 else 0,
                "reply_sentiment": sentiment,
                "top_replying_domains": [{"domain": d, "replies": n} for d, n in top_domains],
                "email_attributed_replies": campaign_reply_count.get(cid, 0),
            }
        )

    results.sort(key=lambda x: x["sent"], reverse=True)

    # Totals
    total_sent = sum(r["sent"] for r in results)
    total_replied = sum(r["replied"] for r in results)
    total_opps = sum(r["opportunities"] for r in results)

    report = {
        "generated_at": datetime.now().isoformat(),
        "period_days": days,
        "totals": {
            "campaigns": len(results),
            "total_sent": total_sent,
            "total_replied": total_replied,
            "total_opportunities": total_opps,
            "overall_reply_rate": round(total_replied / total_sent * 100, 2) if total_sent > 0 else 0,
        },
        "campaigns": results,
    }

    return report, ""


def main():
    parser = argparse.ArgumentParser(description="Instantly Analytics - Campaign Performance Report")
    parser.add_argument("--raw-dir", default="./tmp/instantly-analytics/raw", help="Raw data directory")
    parser.add_argument("--out-dir", default="./tmp/instantly-analytics", help="Output directory")
    parser.add_argument("--days", type=int, default=30, help="Lookback period for reply filtering (default: 30)")
    args = parser.parse_args()

    print(f"Generating campaign performance report (last {args.days}d)...", end="", flush=True)
    report, err = build_campaign_performance(args.raw_dir, args.days)
    if err:
        print(f" FAILED: {err}")
        return

    out_path = os.path.join(args.out_dir, "campaign_performance.json")
    os.makedirs(args.out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    totals = report["totals"]
    print(f" done")
    print(f"  {totals['campaigns']} campaigns, {totals['total_sent']} sent, {totals['total_replied']} replies")
    print(f"  Overall reply rate: {totals['overall_reply_rate']}%, opportunities: {totals['total_opportunities']}")
    print(f"  Saved to: {out_path}")


if __name__ == "__main__":
    main()
