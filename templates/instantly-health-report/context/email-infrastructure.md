# Email Infrastructure Inventory

Last updated: 2026-02-13

## Overview

| Metric | Value |
|--------|-------|
| Total domains | 21 |
| Total accounts | 742 |
| Personas | David Kwint (20 domains), Clara Curbelo (1 domain) |
| Providers | 3 (Google Workspace, Maildoso-style, bulk provider) |

## Domain Groups

### Group A: AutoDemand -- Sending (3-account domains)

Original outbound domains. Google Workspace (provider 2), 3 accounts each, 10-15 daily limit per account.

| Domain | Accts | Limit/Acct | Created | Status | Notes |
|--------|-------|------------|---------|--------|-------|
| autodemandlabs.com | 3 | 15 | 2025-10-26 | sending | Oldest batch |
| automatedemandhq.com | 3 | 15 | 2025-10-26 | sending | Oldest batch |
| automatedemandlabs.com | 3 | 15 | 2025-10-26 | sending | Oldest batch |
| getautodemand.com | 3 | 15 | 2025-10-26 | sending | Oldest batch |
| openautomatedemand.com | 3 | 15 | 2025-10-26 | sending | Oldest batch |
| getautomatedemand.com | 3 | 15 | 2025-09-27 | sending | First domain |
| autodemandhub.com | 3 | 10 | 2025-12-14 | sending | Dec batch |
| autodemandme.com | 3 | 10 | 2025-12-17 | sending | Dec batch |

Persona: David Kwint. Email prefixes: `david@`, `david.k@`, `david.kwint@` (or `davidk@` on older domains).

### Group B: AutoDemand -- Scaled (100-account domains)

High-volume domains using bulk email provider (provider 3). 100 accounts each with varied prefix patterns.

| Domain | Accts | Limit/Acct | Created | Status | Notes |
|--------|-------|------------|---------|--------|-------|
| autodemandworld.com | 100 | 10 | 2025-12-14 | sending | Highest volume (2,290 sent/30d) |
| meetautodemand.com | 100 | 3 | 2025-11-05 | sending | 817 sent/30d |

Persona: David Kwint. Email prefixes: 100 variations (`d.kwint`, `d-kwint`, `d_kwint`, `da-kw`, `dk`, etc.).

### Group C: AutoDemand -- Warmup Only (3-account domains)

Newer domains still in warmup. Google Workspace (provider 2), 3 accounts each, 15 daily limit. Zero campaign sends.

| Domain | Accts | Limit/Acct | Created | Status | Notes |
|--------|-------|------------|---------|--------|-------|
| automatedemandme.com | 3 | 15 | 2025-12-29 | active_warmup | Dec 29 batch |
| automatedemands.com | 3 | 15 | 2025-12-29 | active_warmup | Dec 29 batch |
| automatemydemand.com | 3 | 15 | 2025-12-29 | active_warmup | Dec 29 batch |
| automatethedemand.com | 3 | 15 | 2025-12-29 | active_warmup | Dec 29 batch |
| automateyourdemand.com | 3 | 15 | 2025-12-29 | active_warmup | Dec 29 batch |
| automationdemand.com | 3 | 15 | 2025-12-29 | active_warmup | Dec 29 batch |

Persona: David Kwint. All created 2025-12-29 as a batch. Ready to activate -- warmup scores at 100.

### Group D: GTM/Agent Brand -- Warmup (100-account domains)

New brand identity domains for GTM-focused outreach. Provider 1, 100 accounts each, 1 daily limit (conservative ramp).

| Domain | Accts | Limit/Acct | Created | Status | Persona | Notes |
|--------|-------|------------|---------|--------|---------|-------|
| getagenticgtm.com | 100 | 1 | 2026-01-20 | active_warmup | David Kwint | GTM brand |
| getgtmagents.com | 100 | 1 | 2026-01-20 | active_warmup | David Kwint | GTM brand |
| myagentgtm.com | 100 | 1 | 2026-01-20 | active_warmup | Clara Curbelo | Only Clara domain |
| yourcontextgtm.com | 100 | 1 | 2026-01-20 | active_warmup | David Kwint | GTM brand |

Email prefixes: 100 variations per domain. All created 2026-01-20.

### Group E: Neutral Brand -- Warmup

| Domain | Accts | Limit/Acct | Created | Status | Notes |
|--------|-------|------------|---------|--------|-------|
| easyinboxpro.com | 100 | 10 | 2026-01-18 | active_warmup | Neutral/generic domain |

Persona: David Kwint. Provider 3. Warmup score 100, 980 daily limit capacity.

## Provider Reference

| Code | Type | Typical Limit | Domains Using |
|------|------|---------------|---------------|
| 1 | Bulk (low limit) | 1/acct | Group D (GTM brand, 400 accts) |
| 2 | Google Workspace | 10-15/acct | Groups A + C (42 accts) |
| 3 | Bulk (high limit) | 3-10/acct | Groups B + E (300 accts) |

## Capacity Summary

| Group | Domains | Accounts | Daily Limit (total) | Status |
|-------|---------|----------|---------------------|--------|
| A: AutoDemand Sending | 8 | 24 | 310 | Active campaigns |
| B: AutoDemand Scaled | 2 | 200 | 1,300 | Active campaigns |
| C: AutoDemand Warmup | 6 | 18 | 270 | Ready to activate |
| D: GTM Brand Warmup | 4 | 400 | 400 | Building reputation |
| E: Neutral Warmup | 1 | 100 | 980 | Building reputation |
| **Total** | **21** | **742** | **3,260** | |

## API Endpoint Reference

The Instantly API v2 endpoints used to gather this data:

| Endpoint | Method | Date Filter? | What It Returns |
|----------|--------|-------------|-----------------|
| `/accounts` | GET | No | All email accounts with `warmup_status`, `stat_warmup_score`, `daily_limit`, `provider_code` |
| `/accounts/analytics/daily` | GET | **Yes** (`start_date`, `end_date`) | Per-account daily sent/bounced counts |
| `/campaigns/analytics` | GET | No | All-time cumulative per-campaign metrics (sent, replied, bounced, opps) |
| `/emails` | GET | **No request param** | Returns all replies. Each record has `timestamp_created` -- report scripts filter client-side |
| `/accounts/warmup-analytics` | POST | No | Warmup health scores per account (batched by 50) |

**Key gotcha**: `/emails` has no server-side date filter, so `fetch_data.py` downloads all replies. Each record has `timestamp_created` and `timestamp_email` -- report scripts filter by `timestamp_created >= now - N days` to match the sent data window.
