# CloudNova Agents

Autonomous business-development workforce for CloudNova PaymentOps.

## Schedule

- Runs **once daily at 07:30 Europe/Rome** (`30 7 * * *`).
- Scheduled by the `cloudnova-workforce` CronJob in
  `clusters/hetzner-dr/apps/cloudnova-agents/workforce/cronjob.yaml`.

## What a run does

1. CEO / Strategy Agent (Ollama) produces a research brief.
2. Real web research via DDGS.
3. Deterministic prospect filtering and evidence checks.
4. SQLite deduplication (`/data/leads.db`, schema unchanged).
5. Outreach draft generation (drafts only).
6. Operations / Quality Agent review.
7. One daily summary email to the operator.

## Email behaviour

- **The only email ever sent is the daily summary report, and it goes only to
  the operator (`DAILY_REPORT_TO`).**
- **No prospect/candidate emails are ever sent automatically.**
- All prospect outreach is **DRAFT ONLY** and remains
  `HUMAN_REVIEW_REQUIRED` until a human approves it.
- The report is sent at the very end of the run over **SMTP over SSL**
  (`smtplib.SMTP_SSL`) using the Python standard library. There is exactly one
  SMTP send action per run.
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
SMTP_HOST   # default: cloudnova.tech
SMTP_PORT   # default: 465 (SMTP over SSL)
```

## Run status

The system-level run status is deterministic and never chosen by the LLM:

- `NO_NEW_LEADS` when zero new leads were found.
- `HUMAN_REVIEW_REQUIRED` when one or more new leads were found.
- `ERROR` only when the main workflow itself fails.
