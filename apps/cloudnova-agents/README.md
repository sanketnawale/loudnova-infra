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

1. Read persistent research memory (past queries, inspected companies, leads).
2. CEO / Strategy Agent (Ollama) produces a mission-aware research brief.
3. A query planner deliberately chooses **new** search angles (with a mix of
   exploration, follow-up and experimentation), avoiding recently used queries.
4. Real web research via DDGS (mission-specific, de-duplicated queries).
5. Deterministic company validation and first-party evidence checks.
6. SQLite deduplication and enrichment (`/data/leads.db`).
7. Contact discovery for qualified leads (who to approach, from public sources).
8. Draft-only outreach generation for new/enriched qualified leads.
9. Operations / Quality Agent review (zero-lead safe).
10. Persist run metrics, the research audit trail and search history; send one
    operator report email.

## Company validation

Validation is general, not a hard-coded allow-list. A company name is matched
against the evidence domain by normalising legal suffixes, punctuation and
acronyms and comparing brand tokens, concatenations, the acronym and the
registrable domain (including subdomains). This makes these pass:

- `BNY` / `The Bank of New York Mellon` -> `bny.com`
- `Barclays` / `Barclays Bank` -> `barclays.com`
- `BNP Paribas` -> `cashmanagement.bnpparibas.com`
- `Bank of America` -> `cloud.emcom.bankofamerica.com`

Genuine hallucinations and non-commercial bodies still fail: a name that is
neither in the evidence text nor on the company's own domain is rejected, and
Swift, ISO/ISO 20022, central banks, regulators, government and universities
are blocked by name/domain/suffix rules. A company mentioned only on unrelated
media is rejected as a third-party mention.

Generic business words (`bank`, `payments`, `financial`, `global`, `group`,
`services`, `technology`, `systems`, `holdings`, `international`, …) are
non-distinctive: they can never establish a first-party match on their own.
A match needs a strong full-name/label match, a concatenated distinctive-token
match, an acronym match, a distinctive brand token, or a justified
acronym/domain-prefix relationship.

## Legacy lead revalidation

Persisted leads created before the current rules are never deleted. Before an
existing lead is selected for follow-up research, contact discovery, enrichment
or outreach, it is re-checked against the current organisation-type,
disallowed-prospect and first-party-evidence rules. A lead that no longer
qualifies is skipped for active prospecting and recorded as `LEGACY_REJECTED`
in the run's audit trail (`research_results`) and the operator report; its
historical row and status are left untouched. This keeps old Swift / ISO /
regulator / university-style records out of active prospecting while valid
legacy leads (e.g. BNP Paribas) can still be enriched.

## Contact discovery

After a company qualifies, the workforce looks for **public** contact routes:
official website, team/leadership/contact/press pages, then a company LinkedIn
page as a last resort. Every contact carries its source URL. Rules:

- Emails are accepted only when they literally appear on a first-party page at
  the company's registrable domain (a role mailbox or a published work email).
- Personal/free-mail domains are rejected; no email is ever guessed or inferred.
- No private addresses, personal phone numbers, credentials or scraped personal
  data are collected.
- If no public email exists the lead is kept and the report shows
  `NOT PUBLICLY VERIFIED` with an alternative contact (contact page / profile).
- Stronger verified contact information is never overwritten by weaker evidence.

## Research novelty

- `search_history` persists every query (normalised) so the planner avoids
  repeating identical/near-identical queries.
- `research_results` records every inspected result and its decision
  (`QUALIFIED`, `REJECTED` with reason, or `INSPECTED`) as an audit trail.
- Company novelty is explicit: `NEW_COMPANY`,
  `EXISTING_COMPANY_NEW_EVIDENCE`, `EXISTING_COMPANY_NEW_CONTACT`,
  `ALREADY_KNOWN_NO_CHANGE`, `REJECTED`. An existing company is never reported
  as new; a new contact for an old company is contact-enrichment, not a lead.

## Safe page fetching

Promising candidates are inspected with a bounded, SSRF-safe fetcher:
`http`/`https` only, 80/443 only, DNS resolved and private/loopback/link-local/
reserved addresses rejected, a clear User-Agent, a timeout and a response-size
cap. Only text/HTML is read, and only a few pages per candidate are fetched.

## Persistent research memory

Existing lead data is never destroyed. The schema is extended additively with
`CREATE TABLE IF NOT EXISTS` only (no `DROP`/`DELETE`/`TRUNCATE`):

- `leads` (existing, unchanged columns)
- `research_runs` (id, run_timestamp, mission, search_count, results_count,
  qualified_count, new_leads_count, enriched_count, rejected_count, run_status)
- `lead_evidence` (id, company_key, source_url, source_domain,
  evidence_summary, first_party, discovered_at; unique on company_key +
  source_url so identical evidence is not duplicated)
- `lead_contacts` (id, company_key, contact_name, contact_role, contact_email,
  contact_url, contact_type, source_url, confidence, verified_at, first_party;
  unique on company_key + contact_email and company_key + contact_url)
- `search_history` (id, run_id, timestamp, mission, query, normalized_query,
  results_count)
- `research_results` (id, run_id, run_timestamp, mission, query, result_index,
  title, url, domain, snippet, decision, decision_reason, company_key,
  created_at)

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
- Discovered contact emails are **data shown inside the operator report only**.
  They never become SMTP recipients; the report's `To` header is always
  `DAILY_REPORT_TO`.
- All prospect outreach is **DRAFT ONLY** and remains
  `HUMAN_REVIEW_REQUIRED` until a human approves it.
- The report includes `NEW COMPANIES DISCOVERED`, `EXISTING COMPANIES ENRICHED`,
  `CONTACTS DISCOVERED` (role, person if verified, public email or
  `NOT PUBLICLY VERIFIED`, source URL, confidence), `REJECTED CANDIDATES`,
  `SEARCHES PERFORMED` and `NEW SEARCH ANGLES USED`.
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
