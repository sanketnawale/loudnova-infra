import json
import os
import re
import smtplib
import sqlite3
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage

from ddgs import DDGS


OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://ollama:11434/api/generate",
)

MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:3b",
)

DB_PATH = os.getenv(
    "LEADS_DB",
    "/data/leads.db",
)


def _env_port(name, default):
    try:
        return int(
            os.getenv(name, str(default))
        )
    except (TypeError, ValueError):
        return default


SMTP_HOST = os.getenv(
    "SMTP_HOST",
    "cloudnova.tech",
)

SMTP_PORT = _env_port(
    "SMTP_PORT",
    465,
)

SMTP_USERNAME = os.getenv(
    "SMTP_USERNAME",
    "",
)

SMTP_PASSWORD = os.getenv(
    "SMTP_PASSWORD",
    "",
)

DAILY_REPORT_TO = os.getenv(
    "DAILY_REPORT_TO",
    "",
)

DAILY_REPORT_FROM = os.getenv(
    "DAILY_REPORT_FROM",
    "",
)


REJECTION_REASON_KEYS = (
    "banned_domain",
    "public_sector",
    "third_party",
    "hallucinated_company",
    "invalid_type",
    "low_confidence",
)


REJECTION_REASON_LABELS = {
    "banned_domain": "Banned/non-commercial domain",
    "public_sector": "Public-sector/non-commercial prospect",
    "third_party": "Third-party mention",
    "hallucinated_company": "Hallucinated company",
    "invalid_type": "Invalid organization type",
    "low_confidence": "Low confidence",
}


PRODUCT = """
CloudNova PaymentOps is an early-stage ISO 20022 payment validation
and repair platform.

Current target customers:
- banks
- payment service providers
- fintechs
- financial institutions
- payment operations teams

Important product positioning:

- PaymentOps is still an early-stage product.
- Never claim CloudNova is a market leader.
- Never claim PaymentOps is production-proven.
- Never invent customers.
- Never invent transaction volumes.
- Never invent revenue figures.
- Never invent partnerships.
- Never invent certifications.
- Never invent contact information.
- Never invent deployments.
- Never claim PaymentOps guarantees regulatory compliance.
- Never claim PaymentOps prevents fraud.
- Never invent numerical customer qualification thresholds.
- Never claim that an email has been sent.
- Outreach is DRAFT ONLY.
- Every potential lead requires human verification before outreach.
"""


SEARCH_QUERIES = [
    '"ISO 20022" bank payment modernization',
    '"ISO 20022" payment service provider',
    '"ISO 20022" fintech payments',
    '"ISO 20022" payment operations bank',
    '"ISO 20022" payment validation financial institution',
]


ALLOWED_ORGANIZATION_TYPES = {
    "BANK",
    "PSP",
    "FINTECH",
    "FINANCIAL_INSTITUTION",
}


BANNED_ORGANIZATION_NAMES = {
    "example bank",
    "federal reserve financial services",
    "federal reserve bank",
    "federal reserve",
    "fedpayments improvement",
    "fedpaymentsimprovement",
    "gsdcouncil",
    "gsd council",
}


BANNED_DOMAIN_PATTERNS = {
    "federalreserve.gov",
    "frbservices.org",
    "fedpaymentsimprovement.org",
    "minneapolisfed.org",
    "gsdcouncil.org",
    "gsdso.org",
}


BANNED_TITLE_OR_SNIPPET_PATTERNS = {
    "federal reserve financial services",
    "fedpayments improvement",
    "gsdcouncil",
    "gsd council",
}


BANNED_DOMAIN_SUFFIXES = (
    ".gov",
    ".mil",
    ".edu",
)


NON_COMMERCIAL_DOMAIN_HINTS = {
    "centralbank",
    "central-bank",
    "bis.org",
    "ecb.europa.eu",
    "imf.org",
    "worldbank.org",
    "bankofengland.co.uk",
    "europa.eu",
    "iso.org",
    "wikipedia.org",
}


GENERIC_NAME_TOKENS = {
    "the", "and", "of", "for",
    "bank", "banking",
    "financial", "finance",
    "group", "holdings",
    "services", "service",
    "payments", "payment",
    "international", "global", "national",
    "corporation", "corp", "company",
    "limited", "inc", "llc", "plc", "ltd",
    "ag", "sa", "nv", "se",
}


ACRONYM_STOPWORDS = {
    "the", "and", "of", "for",
}


def domain_from_url(url):
    if not url:
        return ""

    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""

    host = host.split("@")[-1].split(":")[0]

    if host.startswith("www."):
        host = host[4:]

    return host


def name_tokens(name):
    words = re.findall(r"[a-z0-9]+", name.lower())

    return [
        word
        for word in words
        if len(word) >= 3 and word not in GENERIC_NAME_TOKENS
    ]


def name_acronym(name):
    words = re.findall(r"[a-z]+", name.lower())

    return "".join(
        word[0]
        for word in words
        if word not in ACRONYM_STOPWORDS
    )


def evidence_is_first_party(name, source):
    url = source.get("url", "") if isinstance(source, dict) else str(source or "")
    domain = domain_from_url(url)
    tokens = name_tokens(name)
    acronym = name_acronym(name)

    if len(acronym) >= 3 and acronym in domain:
        return True

    for token in tokens:
        if token in domain:
            return True

    if not isinstance(source, dict):
        return False

    title = source.get("title", "").lower()

    if name.lower() in title:
        return True

    for token in tokens:
        if len(token) >= 4 and token in title:
            return True

    return False


def is_disallowed_prospect(name, source):
    name_l = name.lower()
    url = source.get("url", "") if isinstance(source, dict) else str(source or "")
    domain = domain_from_url(url)

    for banned in BANNED_ORGANIZATION_NAMES:
        if banned in name_l:
            return True, "NON-COMMERCIAL / PUBLIC-SECTOR PROSPECT"

    for pattern in BANNED_DOMAIN_PATTERNS:
        if pattern in domain:
            return True, "BANNED DOMAIN"

    if domain.endswith(BANNED_DOMAIN_SUFFIXES):
        return True, "NON-COMMERCIAL / PUBLIC-SECTOR PROSPECT"

    for hint in NON_COMMERCIAL_DOMAIN_HINTS:
        if hint in domain:
            return True, "NON-COMMERCIAL / PUBLIC-SECTOR PROSPECT"

    if isinstance(source, dict):
        text = (
            source.get("title", "")
            + " "
            + source.get("snippet", "")
        ).lower()

        for pattern in BANNED_TITLE_OR_SNIPPET_PATTERNS:
            if pattern in text:
                return True, "NON-COMMERCIAL / PUBLIC-SECTOR PROSPECT"

    return False, ""


def ollama(prompt, max_tokens=500):
    body = json.dumps(
        {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "num_predict": max_tokens,
                "temperature": 0.2,
            },
        }
    ).encode()

    request = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=300,
    ) as response:
        result = json.loads(
            response.read().decode()
        )

    return result["response"].strip()


def init_db():
    os.makedirs(
        os.path.dirname(DB_PATH),
        exist_ok=True,
    )

    conn = sqlite3.connect(DB_PATH)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            company_key TEXT PRIMARY KEY,
            company TEXT NOT NULL,
            source_url TEXT NOT NULL,
            why_fit TEXT,
            target_role TEXT,
            confidence INTEGER,
            first_seen TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )

    conn.commit()

    return conn


def company_key(name):
    return re.sub(
        r"[^a-z0-9]+",
        "",
        name.lower(),
    )


def new_rejection_stats():
    return {
        reason: 0
        for reason in REJECTION_REASON_KEYS
    }


def new_rejection_examples():
    return {
        reason: []
        for reason in REJECTION_REASON_KEYS
    }


def record_rejection(
    rejection_stats,
    rejection_examples,
    reason,
    detail,
    max_examples=3,
):
    if reason not in rejection_stats:
        return

    rejection_stats[reason] += 1

    bucket = rejection_examples.get(reason)

    if bucket is None or len(bucket) >= max_examples:
        return

    detail = str(detail or "").strip()

    if detail:
        bucket.append(detail)


def real_web_search():
    all_results = []
    seen_urls = set()

    ddgs = DDGS(
        timeout=20,
    )

    for query in SEARCH_QUERIES:
        print(
            f"\nWEB SEARCH: {query}",
            flush=True,
        )

        try:
            results = ddgs.text(
                query,
                region="wt-wt",
                safesearch="moderate",
                max_results=5,
            )

        except Exception as exc:
            print(
                f"Search failed: {exc}",
                flush=True,
            )
            continue

        for item in results:
            url = item.get(
                "href",
                "",
            )

            if not url:
                continue

            if url in seen_urls:
                continue

            seen_urls.add(url)

            all_results.append(
                {
                    "title": item.get(
                        "title",
                        "",
                    )[:300],
                    "url": url,
                    "snippet": item.get(
                        "body",
                        "",
                    )[:700],
                }
            )

    return all_results[:20]


def extract_verified_leads(
    results,
    rejection_stats,
    rejection_examples,
):
    indexed_results = []

    for index, item in enumerate(results):
        indexed_results.append(
            {
                "id": index,
                "title": item["title"],
                "url": item["url"],
                "snippet": item["snippet"],
            }
        )

    print(
        "\nSEARCH RESULT SAMPLE:",
        flush=True,
    )

    for item in indexed_results[:5]:
        print(
            (
                f"[{item['id']}] "
                f"{item['title']} "
                f"-> {item['url']}"
            ),
            flush=True,
        )

    evidence = json.dumps(
        indexed_results,
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
You are CloudNova's strict evidence-validation Research Agent.

PRODUCT:
{PRODUCT}

Below are REAL WEB SEARCH RESULTS.

Every result has an integer ID.

{evidence}

Your task is to identify at most 5 genuine potential CUSTOMER
organizations for CloudNova PaymentOps.

Return ONLY a valid JSON array.

Required format:

[
  {{
    "result_index": 1,
    "company": "BNY",
    "organization_type": "BANK",
    "why_fit": "The supplied search result directly discusses BNY's ISO 20022 activity.",
    "target_role": "Head of Payments",
    "confidence": 80
  }}
]

Allowed organization_type values ONLY:

- BANK
- PSP
- FINTECH
- FINANCIAL_INSTITUTION

STRICT RULES:

- result_index MUST refer to one of the supplied results.
- The company name MUST literally appear in the supplied title or snippet.
- Never invent placeholder companies such as "Example Bank".
- Never manufacture a company name from the topic of an article.
- Evidence must refer to the organization itself.
- The organization must be a plausible COMMERCIAL CUSTOMER of PaymentOps.
- Prefer the organization's OWN website, newsroom, or blog as evidence.
- A company mentioned only inside another vendor's article is not a lead.

Reject:

- regulators
- central banks
- government agencies
- public payment infrastructure operators
- standards bodies
- media/news websites
- bloggers
- consulting companies
- training companies
- certification companies
- universities
- research organizations
- generic educational websites
- software vendors selling competing payment products
- companies mentioned only incidentally

Prefer evidence concerning:

- public ISO 20022 migration initiative
- payment modernization project
- ISO 20022 readiness page
- payment transformation initiative
- structured payment data initiative
- payment operations modernization
- public mention of payment validation or transformation requirements

Do not invent:

- contacts
- transaction volumes
- revenue
- employee counts
- customers
- integrations
- compliance status
- regulatory certifications
- operational problems not mentioned in evidence

confidence must be between 0 and 100.

Do NOT try to fill all 5 slots.

Returning 0, 1 or 2 strong candidates is better than returning
weak or invented candidates.
"""

    raw = ollama(
        prompt,
        max_tokens=1200,
    )

    match = re.search(
        r"\[[\s\S]*\]",
        raw,
    )

    if not match:
        print(
            "Research Agent returned no JSON array.",
            flush=True,
        )
        print(
            f"RAW RESPONSE:\n{raw}",
            flush=True,
        )
        return []

    try:
        leads = json.loads(
            match.group(0)
        )

    except json.JSONDecodeError:
        print(
            "Research Agent JSON parse failed.",
            flush=True,
        )
        print(
            f"RAW RESPONSE:\n{raw}",
            flush=True,
        )
        return []

    verified = []

    for lead in leads:
        try:
            idx = int(
                lead.get(
                    "result_index"
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if idx < 0 or idx >= len(results):
            continue

        source = results[idx]

        name = str(
            lead.get(
                "company",
                "",
            )
        ).strip()

        if not name:
            continue

        source_text = (
            source["title"]
            + " "
            + source["snippet"]
        ).lower()

        if name.lower() not in source_text:
            print(
                (
                    "REJECT HALLUCINATED COMPANY: "
                    f"{name}"
                ),
                flush=True,
            )
            record_rejection(
                rejection_stats,
                rejection_examples,
                "hallucinated_company",
                name,
            )
            continue

        disallowed, reason = is_disallowed_prospect(
            name,
            source,
        )

        if disallowed:
            print(
                (
                    f"REJECT {reason}: "
                    f"{name} -> "
                    f"{domain_from_url(source['url'])}"
                ),
                flush=True,
            )
            if reason == "BANNED DOMAIN":
                rejection_reason = "banned_domain"
            else:
                rejection_reason = "public_sector"
            record_rejection(
                rejection_stats,
                rejection_examples,
                rejection_reason,
                name,
            )
            continue

        if not evidence_is_first_party(
            name,
            source,
        ):
            print(
                (
                    "REJECT THIRD-PARTY MENTION: "
                    f"{name} -> "
                    f"{domain_from_url(source['url'])}"
                ),
                flush=True,
            )
            record_rejection(
                rejection_stats,
                rejection_examples,
                "third_party",
                name,
            )
            continue

        org_type = str(
            lead.get(
                "organization_type",
                "",
            )
        ).upper().strip()

        if org_type not in ALLOWED_ORGANIZATION_TYPES:
            print(
                (
                    "REJECT NON-TARGET TYPE: "
                    f"{name} ({org_type})"
                ),
                flush=True,
            )
            record_rejection(
                rejection_stats,
                rejection_examples,
                "invalid_type",
                f"{name} ({org_type})",
            )
            continue

        try:
            confidence = int(
                lead.get(
                    "confidence",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            confidence = 0

        if confidence < 60:
            print(
                (
                    "REJECT LOW CONFIDENCE: "
                    f"{name} ({confidence})"
                ),
                flush=True,
            )
            record_rejection(
                rejection_stats,
                rejection_examples,
                "low_confidence",
                f"{name} ({confidence})",
            )
            continue

        verified.append(
            {
                "company": name,
                "organization_type": org_type,
                "source_url": source["url"],
                "why_fit": str(
                    lead.get(
                        "why_fit",
                        "",
                    )
                )[:700],
                "target_role": str(
                    lead.get(
                        "target_role",
                        "Head of Payments",
                    )
                )[:150],
                "confidence": confidence,
            }
        )

    return verified


def deduplicate_leads(leads):
    unique = []
    seen = set()

    for lead in leads:
        key = company_key(
            lead.get(
                "company",
                "",
            )
        )

        if not key:
            continue

        if key in seen:
            print(
                (
                    "SKIP DUPLICATE CANDIDATE: "
                    f"{lead.get('company', '')}"
                ),
                flush=True,
            )
            continue

        seen.add(key)

        unique.append(lead)

    return unique


def save_new_leads(
    conn,
    leads,
):
    new_leads = []

    for lead in leads:
        key = company_key(
            lead["company"]
        )

        existing = conn.execute(
            """
            SELECT company
            FROM leads
            WHERE company_key = ?
            """,
            (key,),
        ).fetchone()

        if existing:
            print(
                (
                    "SKIP DUPLICATE: "
                    f"{lead['company']}"
                ),
                flush=True,
            )
            continue

        conn.execute(
            """
            INSERT INTO leads (
                company_key,
                company,
                source_url,
                why_fit,
                target_role,
                confidence,
                first_seen,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                lead["company"],
                lead["source_url"],
                lead["why_fit"],
                lead["target_role"],
                lead["confidence"],
                datetime.now(
                    timezone.utc
                ).isoformat(),
                "HUMAN_REVIEW_REQUIRED",
            ),
        )

        new_leads.append(
            lead
        )

    conn.commit()

    return new_leads


def create_outreach_for_lead(lead):
    prompt = f"""
You are CloudNova's B2B Outreach Draft Agent.

PRODUCT:
{PRODUCT}

THIS IS EXACTLY ONE COMPANY:

{json.dumps(lead, ensure_ascii=False, indent=2)}

Produce exactly ONE outreach draft for this ONE company.

Output exactly these fields, once:

COMPANY:
TARGET ROLE:
EVIDENCE USED:
SOURCE URL:
SUBJECT:
EMAIL:

STRICT RULES:

- Produce exactly ONE draft.
- Do not repeat the company.
- Do not output multiple alternatives.
- Maximum 120 words in the EMAIL.
- Use only the supplied evidence.
- Never call CloudNova a leader.
- Never claim CloudNova has existing customers.
- Never invent contact names.
- Never invent email addresses.
- Never invent metrics.
- Never invent regulatory certifications.
- Never claim guaranteed compliance.
- Never claim fraud prevention.
- Never claim PaymentOps is production-proven.
- Never imply the recipient already needs or wants PaymentOps.
- Phrase the message as exploratory business development.
- End with a request for a short discovery conversation.
- Do NOT send anything.
- This draft requires explicit human approval.
"""

    return ollama(
        prompt,
        max_tokens=700,
    )


def create_outreach(leads):
    leads = deduplicate_leads(
        leads
    )

    if not leads:
        return (
            "No new qualified leads. "
            "No outreach drafts generated."
        )

    drafts = []

    for lead in leads:
        print(
            (
                "Generating exactly one outreach draft for: "
                f"{lead['company']}"
            ),
            flush=True,
        )

        drafts.append(
            create_outreach_for_lead(
                lead
            )
        )

    separator = (
        "\n\n"
        + "-" * 72
        + "\n\n"
    )

    return separator.join(
        drafts
    )


def operations_review(
    leads,
    outreach,
):
    prompt = f"""
You are CloudNova's strict Business Development Quality Gate.
You are the final challenge before human review. Be skeptical.

PRODUCT:
{PRODUCT}

CANDIDATE LEADS:

{json.dumps(leads, ensure_ascii=False, indent=2)}

OUTREACH DRAFTS:

{outreach}

Independently challenge EVERY lead. Answer each of these questions:

- Is this actually a commercial buyer?
- Is this a regulator or public body?
- Is this a vendor or competitor?
- Is the source first-party (the organization's own site)?
- Does the evidence actually prove ISO 20022 activity by this organization?
- Did the outreach imply unsupported problems?
- Did the outreach imply PaymentOps capabilities beyond the PRODUCT description?

Return:

1. RUN STATUS: PASS or NEEDS REVIEW
2. Number of candidate leads
3. Per-lead challenge findings
4. Unsupported claims found
5. Leads requiring human verification
6. Recommended next action

STRICT RULES:

- Every lead must remain HUMAN_REVIEW_REQUIRED.
- Never recommend sending the email.
- Never say or imply "send the email".
- The only allowed recommendation is exactly:
  "Human review required before external outreach."
- Never say a lead is fully verified merely because a search result exists.
- Search snippets are research evidence, not definitive proof.
- Challenge whether the evidence actually refers to the organization.
- Challenge whether the organization is a plausible commercial PaymentOps buyer.
- Flag regulators, central banks, government bodies, public infrastructure.
- Flag vendors and competing payment software.
- Flag third-party articles and third-party mentions.
- Flag weak evidence.
- Flag generic articles.
- Flag invented companies.
- Flag invented metrics.
- Flag unsupported problems such as errors, fraud, compliance issues,
  high transaction volume, or cost savings.
- Flag compliance guarantees.
- Flag fraud-prevention claims.
- Flag market-leadership claims.
- Flag production-proven claims.
- Flag unsupported PaymentOps capabilities.
- External outreach always requires explicit human approval.

No email has been sent.
"""

    return ollama(
        prompt,
        max_tokens=700,
    )


def print_lead_for_review(lead):
    print(
        "\n--- HUMAN REVIEW REQUIRED ---",
        flush=True,
    )

    print(
        f"Company: {lead['company']}",
        flush=True,
    )

    print(
        (
            "Organization type: "
            f"{lead['organization_type']}"
        ),
        flush=True,
    )

    print(
        (
            "Evidence domain: "
            f"{domain_from_url(lead['source_url'])}"
        ),
        flush=True,
    )

    print(
        f"Evidence URL: {lead['source_url']}",
        flush=True,
    )

    print(
        f"Why fit: {lead['why_fit']}",
        flush=True,
    )

    print(
        f"Target role: {lead['target_role']}",
        flush=True,
    )

    print(
        f"Confidence: {lead['confidence']}",
        flush=True,
    )

    print(
        "Status: HUMAN_REVIEW_REQUIRED",
        flush=True,
    )


def safe_error(message):
    text = str(message or "").strip()

    if SMTP_PASSWORD:
        text = text.replace(
            SMTP_PASSWORD,
            "[redacted]",
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    if not text:
        return "unknown error"

    return text[:300]


def send_daily_report(subject, body):
    if not (
        SMTP_HOST
        and SMTP_PORT
        and SMTP_USERNAME
        and SMTP_PASSWORD
        and DAILY_REPORT_TO
        and DAILY_REPORT_FROM
    ):
        print(
            (
                "DAILY REPORT EMAIL SKIPPED: "
                "email configuration missing"
            ),
            flush=True,
        )
        return False

    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = DAILY_REPORT_FROM
    message["To"] = DAILY_REPORT_TO

    message.set_content(body)

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL(
            SMTP_HOST,
            SMTP_PORT,
            context=context,
            timeout=30,
        ) as smtp:
            smtp.login(
                SMTP_USERNAME,
                SMTP_PASSWORD,
            )
            smtp.send_message(message)

    except Exception as exc:
        print(
            "DAILY REPORT EMAIL FAILED: "
            + safe_error(str(exc)),
            flush=True,
        )
        return False

    print(
        "DAILY REPORT EMAIL SENT",
        flush=True,
    )

    return True


def format_lead_report(lead):
    lines = [
        f"Company: {lead['company']}",
        (
            "Organization type: "
            f"{lead['organization_type']}"
        ),
        (
            "Evidence domain: "
            f"{domain_from_url(lead['source_url'])}"
        ),
        f"Evidence URL: {lead['source_url']}",
        f"Why fit: {lead['why_fit']}",
        f"Target role: {lead['target_role']}",
        f"Confidence: {lead['confidence']}",
        "Status: HUMAN_REVIEW_REQUIRED",
    ]

    return "\n".join(lines)


def build_rejection_summary(
    rejection_stats,
    rejection_examples,
):
    lines = ["REJECTED PROSPECT SUMMARY"]

    for reason in REJECTION_REASON_KEYS:
        lines.append(
            f"- {REJECTION_REASON_LABELS[reason]}: "
            f"{rejection_stats.get(reason, 0)}"
        )

    examples = []

    for reason in REJECTION_REASON_KEYS:
        bucket = rejection_examples.get(reason) or []

        if not bucket:
            continue

        examples.append(
            f"- {REJECTION_REASON_LABELS[reason]}: "
            + ", ".join(bucket[:3])
        )

    if examples:
        lines.append("Examples:")
        lines.extend(examples)

    return "\n".join(lines)


def build_daily_report(
    run_status,
    search_results,
    verified,
    new_leads,
    total,
    review_count,
    rejection_stats,
    rejection_examples,
    outreach,
    review,
):
    lines = [
        "CloudNova Daily Business Workforce Report",
        "",
        (
            "Date: "
            + datetime.now(
                timezone.utc
            ).date().isoformat()
        ),
        f"Run status: {run_status}",
        "",
        "SEARCH SUMMARY",
        (
            "- Real search results collected: "
            f"{len(search_results)}"
        ),
        (
            "- Candidate organizations passing filters: "
            f"{len(verified)}"
        ),
        (
            "- New leads after deduplication: "
            f"{len(new_leads)}"
        ),
        f"- Total leads currently in memory: {total}",
        f"- Leads waiting for human review: {review_count}",
        "",
        "NEW QUALIFIED LEADS",
    ]

    if new_leads:
        for lead in new_leads:
            lines.append("")
            lines.append(
                format_lead_report(lead)
            )
    else:
        lines.append(
            "No new qualified commercial prospects "
            "were found in this run."
        )

    lines.append("")
    lines.append(
        build_rejection_summary(
            rejection_stats,
            rejection_examples,
        )
    )

    lines.append("")
    lines.append("OUTREACH DRAFTS")
    lines.append(
        outreach
        or "No outreach drafts generated."
    )

    lines.append("")
    lines.append("OPERATIONS REVIEW")
    lines.append(
        review
        or "No operations review available."
    )

    lines.append("")
    lines.append("FINAL SAFETY NOTE")
    lines.append(
        "NO EXTERNAL PROSPECT EMAILS WERE SENT."
    )
    lines.append(
        "ALL PROSPECT OUTREACH REQUIRES HUMAN APPROVAL."
    )

    return "\n".join(lines)


def run_workforce(
    rejection_stats,
    rejection_examples,
):
    print(
        "=" * 72,
        flush=True,
    )

    print(
        "CLOUDNOVA AUTONOMOUS BUSINESS WORKFORCE",
        flush=True,
    )

    print(
        datetime.now(
            timezone.utc
        ).isoformat(),
        flush=True,
    )

    print(
        "=" * 72,
        flush=True,
    )

    conn = init_db()

    print(
        "\n[1/4] CEO / STRATEGY AGENT",
        flush=True,
    )

    strategy = ollama(
        f"""
You are CloudNova's CEO Strategy Agent.

{PRODUCT}

Produce a short research brief using EXACTLY these four sections:

A. TARGET CUSTOMER CATEGORIES
B. RESEARCH SIGNALS TO LOOK FOR
C. HYPOTHESES TO TEST
D. DISQUALIFICATION SIGNALS

A. TARGET CUSTOMER CATEGORIES
List plausible COMMERCIAL buyer categories only
(for example banks, payment service providers, fintechs,
financial institutions, payment operations teams).

B. RESEARCH SIGNALS TO LOOK FOR
List only observable public signals, for example:

- public ISO 20022 migration initiative
- payment modernization project
- ISO 20022 readiness page
- payment transformation initiative
- structured payment data initiative
- payment operations modernization
- public mention of payment validation or transformation requirements

C. HYPOTHESES TO TEST
State hypotheses, never facts. For example:

- PaymentOps may be relevant where ISO 20022 validation or repair
  creates operational work. This must be verified before outreach.

D. DISQUALIFICATION SIGNALS
List reasons to reject a prospect, for example:

- regulators, central banks, government agencies
- public payment infrastructure organizations
- standards bodies
- universities, training or certification organizations
- media, news websites, generic blogs
- consultants
- competing payment software vendors
- third-party articles that only mention the organization

Keep the answer below 300 words.

STRICT RULES:

- Do NOT claim the prospect has errors.
- Do NOT claim the prospect has compliance problems.
- Do NOT claim the prospect has fraud problems.
- Do NOT claim high transaction volumes.
- Do NOT claim cost savings.
- Do NOT invent numerical thresholds.
- Do NOT describe unverified customer problems as facts.
- Do NOT claim PaymentOps guarantees regulatory compliance.
- Do NOT claim PaymentOps prevents fraud.
- Do NOT describe PaymentOps as production-proven.
- Use hypotheses and research signals only.
""",
        max_tokens=400,
    )

    print(
        strategy,
        flush=True,
    )

    print(
        "\n[2/4] REAL WEB RESEARCH AGENT",
        flush=True,
    )

    search_results = real_web_search()

    print(
        (
            "\nCollected "
            f"{len(search_results)} "
            "real web results."
        ),
        flush=True,
    )

    verified = extract_verified_leads(
        search_results,
        rejection_stats,
        rejection_examples,
    )

    print(
        (
            "\nCandidate organizations passing "
            f"automated filters: {len(verified)}"
        ),
        flush=True,
    )

    unique_leads = deduplicate_leads(
        verified
    )

    new_leads = save_new_leads(
        conn,
        unique_leads,
    )

    print(
        (
            "NEW organizations after "
            f"deduplication: {len(new_leads)}"
        ),
        flush=True,
    )

    for lead in new_leads:
        print_lead_for_review(
            lead
        )

    print(
        "\n[3/4] OUTREACH DRAFT AGENT",
        flush=True,
    )

    outreach = create_outreach(
        new_leads
    )

    print(
        outreach,
        flush=True,
    )

    print(
        "\n[4/4] OPERATIONS / REVIEW AGENT",
        flush=True,
    )

    review = operations_review(
        new_leads,
        outreach,
    )

    print(
        review,
        flush=True,
    )

    total = conn.execute(
        """
        SELECT COUNT(*)
        FROM leads
        """
    ).fetchone()[0]

    review_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM leads
        WHERE status = 'HUMAN_REVIEW_REQUIRED'
        """
    ).fetchone()[0]

    print(
        "\n" + "=" * 72,
        flush=True,
    )

    print(
        f"TOTAL UNIQUE LEADS IN MEMORY: {total}",
        flush=True,
    )

    print(
        (
            "LEADS WAITING FOR HUMAN REVIEW: "
            f"{review_count}"
        ),
        flush=True,
    )

    print(
        "NO PROSPECT EMAILS WERE SENT",
        flush=True,
    )

    print(
        "WORKFORCE RUN COMPLETE",
        flush=True,
    )

    print(
        "=" * 72,
        flush=True,
    )

    conn.close()

    return {
        "search_results": search_results,
        "verified": verified,
        "new_leads": new_leads,
        "outreach": outreach,
        "review": review,
        "total": total,
        "review_count": review_count,
    }


def main():
    rejection_stats = new_rejection_stats()
    rejection_examples = new_rejection_examples()

    run_status = "NO_NEW_LEADS"

    data = {
        "search_results": [],
        "verified": [],
        "new_leads": [],
        "outreach": "",
        "review": "",
        "total": 0,
        "review_count": 0,
    }

    try:
        data = run_workforce(
            rejection_stats,
            rejection_examples,
        )

        if data["new_leads"]:
            run_status = "HUMAN_REVIEW_REQUIRED"
        else:
            run_status = "NO_NEW_LEADS"

    except Exception as exc:
        run_status = "ERROR"
        print(
            (
                "WORKFORCE RUN FAILED: "
                + safe_error(str(exc))
            ),
            flush=True,
        )

    print(
        f"\nRUN STATUS: {run_status}",
        flush=True,
    )

    report_subject = (
        "CloudNova Daily Business Workforce Report - "
        + datetime.now(
            timezone.utc
        ).date().isoformat()
    )

    report_body = build_daily_report(
        run_status,
        data["search_results"],
        data["verified"],
        data["new_leads"],
        data["total"],
        data["review_count"],
        rejection_stats,
        rejection_examples,
        data["outreach"],
        data["review"],
    )

    send_daily_report(
        report_subject,
        report_body,
    )


if __name__ == "__main__":
    main()
