import json
import os
import re
import sqlite3
import urllib.request
from datetime import datetime, timezone

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
    "gsdcouncil",
}


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


def extract_verified_leads(results):
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
- The organization must be a plausible CUSTOMER of PaymentOps.

Reject:

- regulators
- central banks
- government organizations
- public payment infrastructure operators
- media/news websites
- bloggers
- consulting companies
- training companies
- certification companies
- standards organizations
- universities
- research organizations
- generic educational websites
- software vendors selling competing payment products
- companies mentioned only incidentally

Prefer evidence concerning:

- ISO 20022 migration
- payment modernization
- payment operations
- payment infrastructure
- payment message processing
- payment data quality
- payment transformation

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

        org_type = str(
            lead.get(
                "organization_type",
                "",
            )
        ).upper().strip()

        if org_type not in ALLOWED_ORGANIZATION_TYPES:
            print(
                (
                    "REJECT INVALID ORGANIZATION TYPE: "
                    f"{name} ({org_type})"
                ),
                flush=True,
            )
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
            continue

        if name.lower() in BANNED_ORGANIZATION_NAMES:
            print(
                (
                    "REJECT NON-TARGET: "
                    f"{name}"
                ),
                flush=True,
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


def create_outreach(leads):
    if not leads:
        return (
            "No new qualified leads. "
            "No outreach drafts generated."
        )

    prompt = f"""
You are CloudNova's B2B Outreach Draft Agent.

PRODUCT:
{PRODUCT}

CANDIDATE LEADS REQUIRING HUMAN REVIEW:

{json.dumps(leads, ensure_ascii=False, indent=2)}

For each candidate create a short personalized outreach DRAFT.

For each draft provide:

COMPANY:
TARGET ROLE:
EVIDENCE USED:
SOURCE URL:
SUBJECT:
EMAIL:

STRICT RULES:

- Maximum 120 words per email.
- Use only the supplied evidence.
- Never call CloudNova a leader.
- Never claim CloudNova has existing bank customers.
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
- Every draft requires explicit human approval.
"""

    return ollama(
        prompt,
        max_tokens=1200,
    )


def operations_review(
    leads,
    outreach,
):
    prompt = f"""
You are CloudNova's strict Business Development Quality Gate.

PRODUCT:
{PRODUCT}

CANDIDATE LEADS:

{json.dumps(leads, ensure_ascii=False, indent=2)}

OUTREACH DRAFTS:

{outreach}

Return:

1. RUN STATUS: PASS or NEEDS REVIEW
2. Number of candidate leads
3. Unsupported claims found
4. Leads requiring human verification
5. Recommended next action

STRICT RULES:

- Every lead requires human verification before outreach.
- Never recommend automatically sending an email.
- Never say a lead is fully verified merely because a search result exists.
- Search snippets are research evidence, not definitive proof.
- Check whether the evidence actually refers to the organization.
- Check whether the organization is a plausible PaymentOps buyer.
- Flag weak evidence.
- Flag generic articles.
- Flag invented companies.
- Flag invented metrics.
- Flag compliance guarantees.
- Flag fraud-prevention claims.
- Flag market-leadership claims.
- Flag unsupported PaymentOps capabilities.
- External outreach always requires explicit human approval.
- The correct next step is normally HUMAN REVIEW of the evidence
  and outreach draft before any external action.

No email has been sent.
"""

    return ollama(
        prompt,
        max_tokens=600,
    )


def main():
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

For today's research run define:

- target customer profile
- primary business problem
- qualitative qualification criteria
- what evidence the Research Agent should look for

Keep the answer below 250 words.

STRICT RULES:

- Never invent numerical qualification thresholds.
- Never invent transaction volumes.
- Never invent revenue.
- Never invent company size.
- Never invent customer problems.
- Do not claim PaymentOps guarantees regulatory compliance.
- Do not claim PaymentOps prevents fraud.
- Do not describe PaymentOps as production-proven.
- Use qualitative qualification criteria unless supported by evidence.
""",
        max_tokens=350,
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
        search_results
    )

    new_leads = save_new_leads(
        conn,
        verified,
    )

    print(
        (
            "Candidate organizations passing "
            f"automated filters: {len(verified)}"
        ),
        flush=True,
    )

    print(
        (
            "NEW organizations after "
            f"deduplication: {len(new_leads)}"
        ),
        flush=True,
    )

    for lead in new_leads:
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
            f"Evidence: {lead['source_url']}",
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
        "NO EMAILS WERE SENT",
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


if __name__ == "__main__":
    main()