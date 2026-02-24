#!/usr/bin/env python3
"""
Build the Email Infrastructure Health Report HTML from JSON data.

Reads the 3 instantly-analytics JSON reports + base template,
applies benchmark thresholds, generates deterministic HTML with
placeholder slots for LLM-generated content.

All output uses inline styles and table-based layouts for email client
compatibility (Gmail, Outlook, Apple Mail).

Usage:
    python build_report_html.py [--data-dir DIR] [--template PATH] [--output PATH]

Outputs HTML with two placeholders for LLM injection:
    {{EXECUTIVE_SUMMARY}} - 2-3 sentence overview
    {{RECOMMENDATIONS}}   - 3-5 strategic recommendations as <li> items
"""

import argparse
import json
import os
import sys
from datetime import datetime


# --- Colors (inlined, no CSS variables) ---

C = {
    "primary": "#005047",
    "secondary": "#00795e",
    "success": "#219653",
    "danger": "#D34053",
    "warning": "#FFA70B",
    "warning_text": "#b45309",
    "gray_50": "#f9fafb",
    "gray_100": "#f3f4f6",
    "gray_200": "#e5e7eb",
    "gray_500": "#6b7280",
    "gray_600": "#4b5563",
    "gray_700": "#374151",
    "gray_900": "#111827",
}

# --- Benchmarks ---

BOUNCE_THRESHOLDS = {"healthy": 2.0, "warning": 5.0}
REPLY_THRESHOLDS = {"below_avg": 1.0, "avg": 5.0, "good": 10.0}
UTILIZATION_THRESHOLDS = {"under": 10.0, "healthy_low": 20.0, "healthy_high": 60.0, "over": 80.0}


def load_json(path):
    with open(path) as f:
        return json.load(f)


def badge_html(text, style):
    colors = {
        "action": (f"rgba(211,64,83,0.1)", C["danger"]),
        "success": (f"rgba(33,150,83,0.1)", C["success"]),
        "warning": (f"rgba(255,167,11,0.1)", C["warning_text"]),
        "primary": (f"rgba(0,80,71,0.1)", C["primary"]),
    }
    bg, fg = colors.get(style, ("rgba(0,80,71,0.1)", C["primary"]))
    return f'<span style="display: inline-block; padding: 4px 10px; border-radius: 100px; font-size: 12px; font-weight: 500; background: {bg}; color: {fg};">{text}</span>'


def bounce_badge(rate):
    if rate > BOUNCE_THRESHOLDS["warning"]:
        return badge_html(f"{rate:.1f}%", "action")
    elif rate > BOUNCE_THRESHOLDS["healthy"]:
        return badge_html(f"{rate:.1f}%", "warning")
    else:
        return badge_html(f"{rate:.2f}%", "success")


def reply_badge(rate):
    if rate >= REPLY_THRESHOLDS["avg"]:
        return badge_html(f"{rate:.1f}%", "success")
    elif rate >= REPLY_THRESHOLDS["below_avg"]:
        return badge_html(f"{rate:.1f}%", "primary")
    else:
        return badge_html(f"{rate:.2f}%", "warning")


def color_for_bounce(rate):
    if rate > BOUNCE_THRESHOLDS["warning"]:
        return C["danger"]
    elif rate > BOUNCE_THRESHOLDS["healthy"]:
        return C["warning_text"]
    return C["success"]


def color_for_reply(rate):
    if rate >= REPLY_THRESHOLDS["below_avg"]:
        return C["success"]
    return C["warning_text"]


# --- Action Item Builder ---

def build_action_items(domain_health, campaign_perf, inbox_status):
    p0, p1, p2 = [], [], []

    total_bounced = sum(d.get("bounced", 0) for d in domain_health.get("domains", []))

    for d in domain_health.get("domains", []):
        if d["sent"] == 0:
            continue
        name = d["domain"]
        bounced = d.get("bounced", 0)
        if d["bounce_rate"] > BOUNCE_THRESHOLDS["warning"]:
            detail = f"<strong><span style='color: {C['danger']};'>{name}</span> bounce rate at {d['bounce_rate']:.2f}%</strong> -- exceeds 5% threshold. "
            if total_bounced > 0:
                pct_of_total = (bounced / total_bounced) * 100
                detail += f"This domain accounts for {pct_of_total:.0f}% of all bounces ({bounced} of {total_bounced}). "
            detail += "Pause sending, clean list, and audit domain reputation."
            p0.append(detail)
        elif d["bounce_rate"] > BOUNCE_THRESHOLDS["healthy"] and d["reply_rate"] >= 1.0:
            detail = f"<strong><span style='color: {C['danger']};'>{name}</span> bounce rate at {d['bounce_rate']:.2f}%</strong> -- exceeds 2% threshold. "
            detail += f"This domain drives the most replies ({d['reply_rate']:.2f}%) but its deliverability is degrading. "
            if total_bounced > 0:
                pct_of_total = (bounced / total_bounced) * 100
                detail += f"{pct_of_total:.0f}% of bounces come from this single domain ({bounced} of {total_bounced})."
            p0.append(detail)
        elif d["bounce_rate"] > BOUNCE_THRESHOLDS["healthy"]:
            p1.append(f"<strong>{name}</strong> bounce rate at {d['bounce_rate']:.1f}% (warning 2-5%). Investigate list quality and DNS records.")

    low_reply_domains = []
    for d in domain_health.get("domains", []):
        if d["sent"] > 500 and d["reply_rate"] < 0.5:
            low_reply_domains.append(d)
    if len(low_reply_domains) > 3:
        names = ", ".join(d["domain"] for d in sorted(low_reply_domains, key=lambda x: x["reply_rate"])[:3])
        p1.append(f"<strong>{len(low_reply_domains)} domains with sub-0.5% reply rates.</strong> Worst performers: {names}. Review copy/targeting or redistribute volume.")
    else:
        for d in low_reply_domains:
            p1.append(f"<strong>{d['domain']}</strong> reply rate only {d['reply_rate']:.2f}% across {d['sent']} sent. Review copy/targeting.")

    ready_warmup = []
    for d in inbox_status.get("domains", []):
        name = d["domain"]
        if d.get("errored", 0) > 0:
            p0.append(f"<strong>{name}</strong> has {d['errored']} errored account(s). Fix immediately.")
        if d.get("warmup_health_score") and d["warmup_health_score"] < 95:
            p0.append(f"<strong>{name}</strong> warmup health score dropped to {d['warmup_health_score']}. Domain reputation at risk.")
        if d.get("status") == "active_warmup" and d.get("warmup_health_score", 0) >= 99.5:
            ready_warmup.append(d)
        if d.get("status") == "sending" and d.get("daily_limit_capacity", 0) > 0:
            utilization = (d.get("daily_send_volume", 0) / d["daily_limit_capacity"]) * 100
            if utilization < UTILIZATION_THRESHOLDS["under"]:
                p1.append(f"<strong>{name}</strong> using only {utilization:.0f}% of {d['daily_limit_capacity']} daily capacity. Ramp up or reassign.")

    if ready_warmup:
        total_accounts = sum(d.get("total_accounts", 0) for d in ready_warmup)
        names = ", ".join(d["domain"] for d in ready_warmup)
        p1.append(f"<strong>{len(ready_warmup)} warmup domains ready to activate.</strong> {names} ({total_accounts} accounts total, all at 99.5%+ warmup health). Assign to campaigns.")

    for c in campaign_perf.get("campaigns", []):
        name = c["campaign_name"]
        if c["sent"] > 500 and c["reply_rate"] < 0.5:
            p1.append(f"Campaign <strong>{name}</strong> has {c['reply_rate']:.2f}% reply rate across {c['sent']} sent. Review copy and targeting.")
        sentiment = c.get("reply_sentiment", {})
        neg = sentiment.get("negative", 0)
        pos = sentiment.get("positive", 0)
        total_sentiment = neg + pos + sentiment.get("unknown", 0)
        if total_sentiment > 3 and neg > pos:
            p2.append(f"Campaign <strong>{name}</strong> has more negative ({neg}) than positive ({pos}) sentiment. Monitor closely.")

    domains_sending = [d for d in domain_health.get("domains", []) if d["sent"] > 0]
    if len(domains_sending) >= 2:
        reply_rates = sorted(domains_sending, key=lambda d: d["reply_rate"], reverse=True)
        top = reply_rates[0]
        bottom = reply_rates[-1]
        if top["reply_rate"] > 0 and bottom["reply_rate"] > 0:
            ratio = top["reply_rate"] / bottom["reply_rate"]
            if ratio > 5:
                p2.append(f"Reply rate spread is {ratio:.0f}x between top ({top['domain']} at {top['reply_rate']:.2f}%) and bottom ({bottom['domain']} at {bottom['reply_rate']:.2f}%).")

    warmup_count = sum(1 for d in inbox_status.get("domains", []) if d.get("status") == "active_warmup")
    if warmup_count > 0:
        p2.append(f"{warmup_count} domain(s) still in warmup. Monitor progress toward activation threshold.")

    return p0, p1, p2


# --- HTML Builders (all inline styles, table-based for email) ---

def _wrap_section(content):
    """Wrap a content section in a table row for the email template."""
    return f"""
          <tr>
            <td style="padding: 32px 40px; border-bottom: 1px solid {C['gray_200']}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;">
              {content}
            </td>
          </tr>"""


def build_summary_cards(domain_health, inbox_status):
    dh = domain_health["totals"]
    ix = inbox_status["totals"]
    sending_count = ix["by_status"].get("sending", 0)
    total_domains = ix["domains"]
    total_accounts = ix["total_accounts"]

    reply_color = color_for_reply(dh["overall_reply_rate"])
    bounce_color = color_for_bounce(dh["overall_bounce_rate"])

    card_style = "text-align: center; padding: 24px 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;"
    number_style = "font-size: 32px; font-weight: 700; line-height: 1.2;"
    label_style = f"font-size: 11px; color: {C['gray_500']}; text-transform: uppercase; letter-spacing: 0.5px; padding-top: 4px;"

    return f"""
          <tr>
            <td style="padding: 0; border-bottom: 1px solid {C['gray_200']};">
              <!--[if mso]><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><![endif]-->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td width="25%" style="{card_style} border-right: 1px solid {C['gray_200']};">
                    <div style="{number_style} color: {C['primary']};">{sending_count} / {total_domains}</div>
                    <div style="{label_style}">Sending Domains</div>
                  </td>
                  <td width="25%" style="{card_style} border-right: 1px solid {C['gray_200']};">
                    <div style="{number_style} color: {reply_color};">{dh['overall_reply_rate']:.2f}%</div>
                    <div style="{label_style}">Reply Rate</div>
                  </td>
                  <td width="25%" style="{card_style} border-right: 1px solid {C['gray_200']};">
                    <div style="{number_style} color: {bounce_color};">{dh['overall_bounce_rate']:.2f}%</div>
                    <div style="{label_style}">Bounce Rate</div>
                  </td>
                  <td width="25%" style="{card_style}">
                    <div style="{number_style} color: {C['primary']};">{total_accounts}</div>
                    <div style="{label_style}">Total Accounts</div>
                  </td>
                </tr>
              </table>
              <!--[if mso]></tr></table><![endif]-->
            </td>
          </tr>"""


def _section_header(icon, title, subtitle=None):
    icon_bg = {
        "action": f"rgba(211,64,83,0.1)",
        "info": f"rgba(0,80,71,0.1)",
        "active": f"rgba(33,150,83,0.1)",
        "warning": f"rgba(255,167,11,0.1)",
    }
    # Determine icon type from title
    bg = icon_bg.get("info")
    if "Action" in title:
        bg = icon_bg["action"]
    elif "Campaign" in title:
        bg = icon_bg["active"]
    elif "Infrastructure" in title:
        bg = icon_bg["warning"]

    subtitle_html = f'<div style="font-size: 13px; color: {C["gray_500"]}; margin: 0;">{subtitle}</div>' if subtitle else ""

    return f"""
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 20px;">
                <tr>
                  <td style="width: 40px; height: 40px; border-radius: 10px; background: {bg}; text-align: center; vertical-align: middle; font-size: 18px;">{icon}</td>
                  <td style="padding-left: 12px; vertical-align: middle;">
                    <div style="font-size: 18px; font-weight: 600; color: {C['gray_900']}; margin: 0;">{title}</div>
                    {subtitle_html}
                  </td>
                </tr>
              </table>"""


def build_executive_summary_section():
    header = _section_header("&#128202;", "Executive Summary")
    content = f"""{header}
              <p style="color: {C['gray_600']}; line-height: 1.7; font-size: 14px; margin: 0;">{{{{EXECUTIVE_SUMMARY}}}}</p>"""
    return _wrap_section(content)


def build_action_items_section(p0, p1, p2):
    header = _section_header("&#127919;", "Action Items", f"Prioritized by urgency")
    items_html = ""

    def priority_block(items, label, label_bg, label_color, item_bg, border_color):
        block = f'<div style="margin-bottom: 20px;">'
        block += f'<div style="margin-bottom: 12px;"><span style="display: inline-block; padding: 4px 12px; background: {label_bg}; color: {label_color}; border-radius: 100px; font-size: 13px; font-weight: 600;">{label}</span></div>'
        for item in items:
            block += f'<div style="padding: 12px 16px; background: {item_bg}; border-left: 3px solid {border_color}; margin-bottom: 8px; border-radius: 0 6px 6px 0; font-size: 14px; color: {C["gray_700"]}; line-height: 1.6;">{item}</div>'
        block += '</div>'
        return block

    if p0:
        items_html += priority_block(p0, "P0 - Act Now", "rgba(211,64,83,0.1)", C["danger"], "rgba(211,64,83,0.04)", C["danger"])
    if p1:
        items_html += priority_block(p1, "P1 - This Week", "rgba(255,167,11,0.1)", C["warning_text"], "rgba(255,167,11,0.04)", C["warning"])
    if p2:
        items_html += priority_block(p2, "P2 - Monitor", "rgba(0,80,71,0.1)", C["primary"], "rgba(0,80,71,0.04)", C["primary"])

    if not (p0 or p1 or p2):
        items_html = f'<div style="text-align: center; padding: 32px; color: {C["gray_500"]};"><div style="font-size: 32px; margin-bottom: 8px;">&#9989;</div><p>No action items -- all metrics within healthy thresholds.</p></div>'

    content = f"{header}{items_html}"
    return _wrap_section(content)


def _data_table(headers, rows_data, col_aligns=None):
    """Build an email-compatible data table with inline styles."""
    th_style = f"text-align: left; padding: 12px 16px; background: {C['gray_50']}; font-weight: 600; color: {C['gray_700']}; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid {C['gray_200']};"
    td_style = f"padding: 14px 16px; border-bottom: 1px solid {C['gray_100']}; color: {C['gray_600']}; font-size: 14px;"
    td_name_style = f"padding: 14px 16px; border-bottom: 1px solid {C['gray_100']}; color: {C['gray_900']}; font-weight: 500; font-size: 14px;"

    if col_aligns is None:
        col_aligns = ["left"] * len(headers)

    thead = "<tr>"
    for i, h in enumerate(headers):
        align = col_aligns[i]
        thead += f'<th style="{th_style} text-align: {align};">{h}</th>'
    thead += "</tr>"

    tbody = ""
    for row in rows_data:
        tbody += "<tr>"
        for i, cell in enumerate(row):
            align = col_aligns[i]
            style = td_name_style if i == 0 else td_style
            tbody += f'<td style="{style} text-align: {align};">{cell}</td>'
        tbody += "</tr>"

    return f"""
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse; font-size: 14px;">
                <thead>{thead}</thead>
                <tbody>{tbody}</tbody>
              </table>"""


def build_domain_table(domain_health):
    sending = [d for d in domain_health["domains"] if d["sent"] > 0]
    sending.sort(key=lambda d: d["reply_rate"], reverse=True)

    header = _section_header("&#128200;", "Domain Performance", f"{len(sending)} sending domains, sorted by reply rate")

    rows = []
    for d in sending:
        rows.append([
            d["domain"],
            f"{d['sent']:,}",
            str(d["replies"]),
            reply_badge(d["reply_rate"]),
            str(d["bounced"]),
            bounce_badge(d["bounce_rate"]),
            str(d["account_count"]),
        ])

    table = _data_table(
        ["Domain", "Sent", "Replies", "Reply %", "Bounced", "Bounce %", "Accounts"],
        rows,
        ["left", "right", "right", "right", "right", "right", "right"],
    )
    return _wrap_section(f"{header}{table}")


def build_campaign_table(campaign_perf):
    campaigns = sorted(campaign_perf["campaigns"], key=lambda c: c["sent"], reverse=True)

    totals = campaign_perf["totals"]
    header = _section_header("&#9889;", "Campaign Performance", f"{totals['campaigns']} campaigns / {totals['total_sent']:,} sent / {totals['total_opportunities']} opportunities")

    rows = []
    for c in campaigns:
        sentiment = c.get("reply_sentiment", {})
        pos = sentiment.get("positive", 0)
        neg = sentiment.get("negative", 0)
        unk = sentiment.get("unknown", 0)
        sentiment_str = f"+{pos} / -{neg} / ?{unk}" if (pos + neg + unk) > 0 else "--"

        status_map = {1: "Active", 2: "Active", 3: "Paused"}
        status = status_map.get(c.get("status"), "Unknown")
        status_badge = badge_html(status, "primary" if status == "Active" else "warning")

        rows.append([
            c["campaign_name"],
            status_badge,
            f"{c['sent']:,}",
            str(c["replied"]),
            reply_badge(c["reply_rate"]),
            str(c["opportunities"]),
            f"{c.get('opportunity_rate', 0):.2f}%",
            sentiment_str,
        ])

    table = _data_table(
        ["Campaign", "Status", "Sent", "Replied", "Reply %", "Opps", "Opp %", "Sentiment"],
        rows,
        ["left", "left", "right", "right", "right", "right", "right", "center"],
    )
    return _wrap_section(f"{header}{table}")


def build_infrastructure_table(inbox_status):
    domains = inbox_status["domains"]
    sending = [d for d in domains if d.get("status") == "sending"]
    warmup = [d for d in domains if d.get("status") == "active_warmup"]

    totals = inbox_status["totals"]
    header = _section_header("&#9888;&#65039;", "Infrastructure Status", f"{totals['domains']} domains / {totals['total_accounts']} accounts / {totals.get('errored_accounts', 0)} errored")

    th_style = f"text-align: left; padding: 12px 16px; background: {C['gray_50']}; font-weight: 600; color: {C['gray_700']}; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid {C['gray_200']};"
    td_style = f"padding: 14px 16px; border-bottom: 1px solid {C['gray_100']}; color: {C['gray_600']}; font-size: 14px;"
    td_name_style = f"padding: 14px 16px; border-bottom: 1px solid {C['gray_100']}; color: {C['gray_900']}; font-weight: 500; font-size: 14px;"
    group_style = f"background: {C['gray_50']}; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: {C['gray_700']}; padding: 8px 16px;"

    headers = ["Domain", "Accounts", "Active", "Errored", "Avg Daily", "Capacity", "Util %", "Warmup"]
    aligns = ["left", "right", "right", "right", "right", "right", "right", "right"]

    thead = "<tr>"
    for i, h in enumerate(headers):
        thead += f'<th style="{th_style} text-align: {aligns[i]};">{h}</th>'
    thead += "</tr>"

    def make_rows(domain_list):
        rows = ""
        for d in sorted(domain_list, key=lambda x: x["total_accounts"], reverse=True):
            util = ""
            if d.get("daily_limit_capacity", 0) > 0 and d.get("daily_send_volume", 0) > 0:
                pct = (d["daily_send_volume"] / d["daily_limit_capacity"]) * 100
                util = f"{pct:.0f}%"
            elif d.get("status") == "active_warmup":
                util = "Warmup"
            else:
                util = "--"
            warmup_score = f"{d['warmup_health_score']}" if d.get("warmup_health_score") else "--"
            cells = [
                d["domain"],
                str(d["total_accounts"]),
                str(d.get("active", 0)),
                str(d.get("errored", 0)),
                f"{d.get('daily_send_volume', 0):.1f}",
                f"{d.get('daily_limit_capacity', 0):,}",
                util,
                warmup_score,
            ]
            rows += "<tr>"
            for i, cell in enumerate(cells):
                style = td_name_style if i == 0 else td_style
                rows += f'<td style="{style} text-align: {aligns[i]};">{cell}</td>'
            rows += "</tr>"
        return rows

    sending_rows = make_rows(sending)
    warmup_rows = make_rows(warmup)

    table = f"""
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse; font-size: 14px;">
                <thead>{thead}</thead>
                <tbody>
                  <tr><td colspan="8" style="{group_style}">Sending ({len(sending)})</td></tr>
                  {sending_rows}
                  <tr><td colspan="8" style="{group_style}">Active Warmup ({len(warmup)})</td></tr>
                  {warmup_rows}
                </tbody>
              </table>"""

    return _wrap_section(f"{header}{table}")


def build_recommendations_section():
    header = _section_header("&#128161;", "Recommendations", "Strategic recommendations based on current data")
    content = f"""{header}
              <ol style="padding-left: 20px; color: {C['gray_600']}; line-height: 1.8; font-size: 14px;">
                {{{{RECOMMENDATIONS}}}}
              </ol>"""
    return _wrap_section(content)


def build_benchmark_reference():
    col_style = "vertical-align: top; padding: 0 12px; font-size: 13px;"
    label_style = f"font-weight: 600; color: {C['gray_700']}; margin-bottom: 8px; padding-bottom: 8px;"

    content = f"""
              {_section_header("&#128218;", "Benchmark Reference", "Cold email industry standards")}
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td width="33%" style="{col_style}">
                    <div style="{label_style}">Bounce Rate</div>
                    <div style="color: {C['success']};">&lt; 2% Healthy</div>
                    <div style="color: {C['warning_text']};">2-5% Warning</div>
                    <div style="color: {C['danger']};">&gt; 5% Critical</div>
                  </td>
                  <td width="33%" style="{col_style}">
                    <div style="{label_style}">Reply Rate</div>
                    <div style="color: {C['warning_text']};">&lt; 1% Below Avg</div>
                    <div style="color: {C['primary']};">1-5% Average</div>
                    <div style="color: {C['success']};">5-10% Good</div>
                  </td>
                  <td width="33%" style="{col_style}">
                    <div style="{label_style}">Utilization</div>
                    <div style="color: {C['warning_text']};">&lt; 10% Under</div>
                    <div style="color: {C['success']};">20-60% Healthy</div>
                    <div style="color: {C['danger']};">&gt; 80% Over</div>
                  </td>
                </tr>
              </table>"""

    return f"""
          <tr>
            <td style="padding: 32px 40px; background-color: {C['gray_50']}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;">
              {content}
            </td>
          </tr>"""


def build_report(data_dir, template_path, output_path):
    domain_health = load_json(os.path.join(data_dir, "domain_health.json"))
    campaign_perf = load_json(os.path.join(data_dir, "campaign_performance.json"))
    inbox_status = load_json(os.path.join(data_dir, "inbox_status.json"))

    with open(template_path) as f:
        template = f.read()

    today = datetime.now().strftime("%Y-%m-%d")

    p0, p1, p2 = build_action_items(domain_health, campaign_perf, inbox_status)

    content = ""
    content += build_summary_cards(domain_health, inbox_status)
    content += build_executive_summary_section()
    content += build_action_items_section(p0, p1, p2)
    content += build_domain_table(domain_health)
    content += build_campaign_table(campaign_perf)
    content += build_infrastructure_table(inbox_status)
    content += build_recommendations_section()
    content += build_benchmark_reference()

    # Fill template
    html = template.replace("{{REPORT_TITLE}}", "Email Infrastructure Health Report")
    html = html.replace("{{REPORT_DATE}}", today)
    html = html.replace("{{CONTENT}}", content)

    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    summary = {
        "output": output_path,
        "date": today,
        "action_items": {"p0": len(p0), "p1": len(p1), "p2": len(p2)},
        "domains_sending": len([d for d in domain_health["domains"] if d["sent"] > 0]),
        "campaigns": len(campaign_perf["campaigns"]),
        "placeholders": ["{{EXECUTIVE_SUMMARY}}", "{{RECOMMENDATIONS}}"],
    }
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Build Email Health Report HTML")
    parser.add_argument("--data-dir", default="./tmp/instantly-analytics",
                        help="Directory with JSON report files")
    parser.add_argument("--template", default=".datagen/instantly-health-report/templates/base-email.html",
                        help="Path to base HTML template")
    parser.add_argument("--output", default=None,
                        help="Output HTML path (default: reports/instantly/health-report-{date}.html)")
    args = parser.parse_args()

    if args.output is None:
        today = datetime.now().strftime("%Y-%m-%d")
        args.output = f"reports/instantly/health-report-{today}.html"

    build_report(args.data_dir, args.template, args.output)


if __name__ == "__main__":
    main()
