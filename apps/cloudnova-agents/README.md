# CloudNova Agents

Autonomous business-development workforce for CloudNova PaymentOps.

## Schedule

- Runs **every 2 hours from 07:30 through 19:30 Europe/Rome**
  (`30 7-19/2 * * *`): 07:30, 09:30, 11:30, 13:30, 15:30, 17:30, 19:30.
- Scheduled by the `cloudnova-workforce` CronJob in
  `clusters/hetzner-dr/apps/cloudnova-agents/workforce/cronjob.yaml`.
- `concurrencyPolicy: Forbid`; each cycle starts, performs its work, sends one
  operator report and terminates. There are no continuously-running agents.

## Rotating research missions

The current Europe/Rome hour deterministically selects a mission
(`get_research_mission()`, using `zoneinfo.ZoneInfo("Europe/Rome")`):

| Time  | Mission                        |
| ----- | ------------------------------ |
| 07:30 | Banks / ISO 20022              |
| 09:30 | PSP / Payment Processors       |
| 11:30 | Fintech                        |
| 13:30 | Europe Research                |
| 15:30 | Middle East Research           |
| 17:30 | Deep Verification / Enrichment |
| 19:30 | Final Discovery + Review       |

Each mission has its own categories, geographies, search queries and
instructions. The 17:30 and 19:30 missions also generate additional searches
from existing `HUMAN_REVIEW_REQUIRED` leads. All evidence URLs come from real
DDGS search results; the LLM never invents URLs.

## What a run does

1. CEO / Strategy Agent (Ollama) produces a mission-aware research brief.
2. Real web research via DDGS (mission-specific queries).
3. Deterministic prospect filtering and first-party evidence checks.
4. SQLite deduplication and enrichment (`/data/leads.db`).
5. Draft-only outreach generation for new/enriched qualified leads.
6. Operations / Quality Agent review (zero-lead safe).
7. Persist run metrics and send one operator report email.

## Persistent research memory

Existing lead data is never destroyed. The schema is extended additively with
`CREATE TABLE IF NOT EXISTS` only (no `DROP`/`DELETE`):

- `leads` (existing, unchanged columns)
- `research_runs` (id, run_timestamp, mission, search_count, results_count,
  qualified_count, new_leads_count, enriched_count, rejected_count, run_status)
- `lead_evidence` (id, company_key, source_url, source_domain,
  evidence_summary, first_party, discovered_at; unique on company_key +
  source_url so identical evidence is not duplicated)

## Deduplication and enrichment

- A company already present in `leads` is never counted as a new lead.
- New evidence is recorded in `lead_evidence`; identical URLs are ignored.
- Existing leads are enriched only when stronger/new evidence is found
  (improved `why_fit`, higher confidence, or a justified target role).
- `HUMAN_REVIEW_REQUIRED` is always retained; only a human may change it.
- Reports distinguish **NEW LEADS THIS RUN**, **ENRICHED EXISTING LEADS** and
  **REJECTED CANDIDATES**.

## Email behaviour

- **The only email ever sent is the operator report, and it goes only to
  `DAILY_REPORT_TO`.**
- **No prospect/candidate emails are ever sent automatically.** No lead,
  prospect, discovered or scraped address is ever used as a recipient.
- All prospect outreach is **DRAFT ONLY** and remains
  `HUMAN_REVIEW_REQUIRED` until a human approves it.
- One report is sent after every run over **SMTP submission with STARTTLS**
  (`smtplib.SMTP` + `starttls`, port 587) using the Python standard library.
  There is exactly one `smtp.send_message(message)` call per run.
- Subject format:
  `CloudNova Workforce Report - <MISSION> - YYYY-MM-DD HH:MM Europe/Rome`.
- If email configuration is missing or sending fails, the workforce does not
  crash; it logs `DAILY REPORT EMAIL SKIPPED` / `DAILY REPORT EMAIL FAILED`
  and a successful research run keeps its status.

## Required Kubernetes Secret

The CronJob references a Secret named:

```text
cloudnova-agent-email
```

with the keys:

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
DAILY_REPORT_TO
DAILY_REPORT_FROM
```

The Secret is referenced with `envFrom.secretRef` and marked `optional: true`
so the workload keeps running and simply skips email delivery until the
Secret exists. **Never commit real secret values to Git.**

SMTP defaults (used when the Secret does not override them):

```text
SMTP_HOST   # default: server376.web-hosting.com
SMTP_PORT   # default: 587 (SMTP submission with STARTTLS)
```

## PaymentOps factual guardrails

CloudNova PaymentOps is early stage. The current implementation is an ISO 20022
`pacs.008` vertical slice with validation/repair-related functionality. Prompts
never claim guaranteed compliance, "ensuring compliance with regulatory
standards", regulatory certification, fraud prevention, production-proven
functionality, market leadership, customer volumes, guaranteed savings or
guaranteed operational improvements.

## Run status

The system-level run status is deterministic and never chosen by the LLM:

- `NO_NEW_LEADS` when no new qualified leads and no meaningful enrichment.
- `NEW_LEADS_REVIEW_REQUIRED` when at least one new qualified lead exists.
- `LEADS_ENRICHED_REVIEW_REQUIRED` when no new leads but existing leads were
  materially enriched.
- `ERROR` only when the main workforce itself fails.

SMTP delivery success/failure is tracked separately and never changes the
research run status.
