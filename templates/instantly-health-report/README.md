# Email Infrastructure Health Report

Weekly email infrastructure health report for Instantly. Fetches domain health, campaign performance, and inbox status analytics, generates a branded HTML report with benchmark-based action items, writes AI-powered strategic recommendations, and emails the final report.

## Architecture

**Hybrid Script + LLM** -- scripts handle 90% of the report (data tables, badges, action items) deterministically. The agent writes only the executive summary and strategic recommendations, then injects them into the HTML.

## Prerequisites

- **INSTANTLY_API_KEY** -- Instantly API v2 key (set in `.env` or environment)
- **DATAGEN_API_KEY** -- DataGen platform API key
- **Gmail MCP** -- Connected in DataGen for email delivery
- **Python packages** -- `requests`, `python-dotenv`, `datagen-python-sdk`

## Quickstart

```bash
# Install dependencies
pip install requests python-dotenv datagen-python-sdk

# Set API keys
export INSTANTLY_API_KEY=your_key
export DATAGEN_API_KEY=your_key

# Run the agent
@instantly-health-report run the email health report
```

## What it does

1. **Fetches raw data** from Instantly API v2 (accounts, analytics, campaigns, replies, warmup)
2. **Generates 3 reports** -- domain health, campaign performance, inbox status
3. **Builds HTML report** with summary cards, data tables, and prioritized action items (P0/P1/P2)
4. **Agent writes** executive summary and strategic recommendations based on all data
5. **Sends via Gmail** with HTML formatting

## File structure

After install, files are placed in `.datagen/instantly-health-report/`:

```
.datagen/instantly-health-report/
  scripts/
    fetch_data.py              # Fetches raw data from Instantly API v2
    report_domain_health.py    # Per-domain deliverability metrics
    report_campaign_perf.py    # Per-campaign funnel + sentiment
    report_inbox_status.py     # Account health + utilization
    build_report_html.py       # Generates HTML with LLM placeholders
  templates/
    base-email.html            # Base HTML email template
  context/
    email-infrastructure.md    # Infrastructure inventory reference
  learnings/
    common_failures_and_fix.md # Accumulated knowledge from runs
```

Intermediate data goes to `tmp/instantly-analytics/`. Final report to `reports/instantly/`.

## Benchmarks

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Bounce Rate | < 2% | 2% - 5% | > 5% |
| Reply Rate | 1% - 5% | < 1% | -- |
| Utilization | 20% - 60% | < 10% or > 80% | -- |
| Warmup Health | >= 95 | < 95 | -- |
