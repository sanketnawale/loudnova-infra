import json
import os
import re
import sqlite3
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

from ddgs import DDGS

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://ollama:11434/api/generate",
)
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
DB_PATH = os.getenv("LEADS_DB", "/data/leads.db")

PRODUCT = """
CloudNova PaymentOps is an ISO 20022 payment validation and repair platform.

Current focus:
- banks
- payment service providers
- fintechs
- payment operations teams

PaymentOps is still an early-stage product.

Rules:
- Never claim CloudNova is a market leader.
- Never invent customers, transaction volumes, certifications, contacts,
  revenue figures, partnerships or production deployments.
- Never claim that an email has been sent.
- Outreach is DRAFT ONLY and requires human approval.
"""

SEARCH_QUERIES = [
    '"ISO 20022" bank payment modernization',
    '"ISO 20022" payment service provider',
    '"ISO 20022" fintech payments',
    '"ISO 20022" payment operations bank',
    '"ISO 20022" payment validation financial institution',
]


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

    req = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=300) as response:
        result = json.loads(response.read().decode())

    return result["response"].strip()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

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
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def real_web_search():
    all_results = []
    seen_urls = set()

    ddgs = DDGS(timeout=20)

    for query in SEARCH_QUERIES:
        print(f"\nWEB SEARCH: {query}", flush=True)

        try:
            results = ddgs.text(
                query,
                region="wt-wt",
                safesearch="moderate",
                max_results=5,
            )
        except Exception as exc:
            print(f"Search failed: {exc}", flush=True)
            continue

        for item in results:
            url = item.get("href", "")

            if not url or url in seen_urls:
                continue

            seen_urls.add(url)

            all_results.append(
                {
                    "title": item.get("title", "")[:300],
                    "url": url,
                    "snippet": item.get("body", "")[:700],
                }
            )

    return all_results[:20]


def extract_verified_leads(results):
    indexed_results = []

    for i, item in enumerate(results):
        indexed_results.append(
            {
                "id": i,
                "title": item["title"],
                "url": item["url"],
                "snippet": item["snippet"],
            }
        )

    print("\nSEARCH RESULT SAMPLE:", flush=True)

    for item in indexed_results[:5]:
        print(
            f"[{item['id']}] {item['title']} -> {item['url']}",
            flush=True,
        )

    evidence = json.dumps(
        indexed_results,
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
You are CloudNova's evidence-validation Research Agent.

PRODUCT:
{PRODUCT}

Below are REAL WEB SEARCH RESULTS.
Every result has an integer ID.

{evidence}

Identify at most 5 potential CUSTOMER organizations.

Return ONLY a JSON array.

Example:

[
  {{
    "result_index": 3,
    "company": "Example Bank",
    "why_fit": "The supplied result explicitly discusses its ISO 20022 payment migration.",
    "target_role": "Head of Payments",
    "confidence": 80
  }}
]

Rules:

- result_index MUST be one of the supplied result IDs.
- Company must actually appear or be clearly identifiable in that result.
- Evidence must concern the organization itself.
- Prefer banks, PSPs, fintechs and financial institutions.
- Prefer evidence about ISO 20022, payment modernization,
  payment operations or payment infrastructure.
- Do not invent names, metrics, transaction volumes or contacts.
- Do not invent facts not present in the result.
- Do not select generic articles unless they clearly identify
  a potential customer organization.
- Do not select CloudNova.
- Do not select an organization merely because it sells competing
  software.
- confidence must be between 0 and 100.
"""

    raw = ollama(prompt, max_tokens=1200)

    match = re.search(r"\[[\s\S]*\]", raw)

    if not match:
        print("Research Agent returned no JSON array.", flush=True)
        print(f"RAW RESPONSE:\n{raw}", flush=True)
        return []

    try:
        leads = json.loads(match.group(0))
    except json.JSONDecodeError:
        print("Research Agent JSON parse failed.", flush=True)
        print(f"RAW RESPONSE:\n{raw}", flush=True)
        return []

    verified = []

    for lead in leads:
        try:
            idx = int(lead.get("result_index"))
        except (TypeError, ValueError):
            continue

        if idx < 0 or idx >= len(results):
            continue

        source = results[idx]

        name = str(lead.get("company", "")).strip()

        if not name:
            continue

        try:
            confidence = int(lead.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0

        if confidence < 50:
            continue

        verified.append(
            {
                "company": name,
                "source_url": source["url"],
                "why_fit": str(lead.get("why_fit", ""))[:700],
                "target_role": str(
                    lead.get("target_role", "Head of Payments")
                )[:150],
                "confidence": confidence,
            }
        )

    return verified

def save_new_leads(conn, leads):
    new_leads = []

    for lead in leads:
        key = company_key(lead["company"])

        existing = conn.execute(
            "SELECT company FROM leads WHERE company_key = ?",
            (key,),
        ).fetchone()

        if existing:
            print(
                f"SKIP DUPLICATE: {lead['company']}",
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
                datetime.now(timezone.utc).isoformat(),
                "RESEARCHED",
            ),
        )

        new_leads.append(lead)

    conn.commit()
    return new_leads


def create_outreach(leads):
    if not leads:
        return "No new qualified leads. No outreach drafts generated."

    prompt = f"""
You are CloudNova's B2B Outreach Agent.

PRODUCT:
{PRODUCT}

VERIFIED LEADS:

{json.dumps(leads, ensure_ascii=False, indent=2)}

For each lead write a very short personalized B2B outreach DRAFT.

For each draft provide:

COMPANY:
TARGET ROLE:
EVIDENCE USED:
SUBJECT:
EMAIL:

Rules:

- Maximum 120 words per email.
- Use only evidence provided above.
- Do not call CloudNova a leader.
- Do not claim existing customers.
- Do not invent names.
- Do not invent metrics.
- Do not invent regulatory certifications.
- Do not send anything.
- End with a request for a short discovery conversation.
"""

    return ollama(prompt, max_tokens=1200)


def operations_review(leads, outreach):
    prompt = f"""
You are CloudNova's Operations and Quality Agent.

Review this run.

VERIFIED NEW LEADS:
{json.dumps(leads, ensure_ascii=False, indent=2)}

OUTREACH DRAFTS:
{outreach}

Return:

1. RUN STATUS: PASS or NEEDS REVIEW
2. Number of verified new leads
3. Any unsupported claims
4. Leads requiring human verification
5. Recommended next action

Important:
No email has been sent.
Human approval is mandatory before external outreach.
"""

    return ollama(prompt, max_tokens=500)


def main():
    print("=" * 72, flush=True)
    print("CLOUDNOVA AUTONOMOUS BUSINESS WORKFORCE", flush=True)
    print(datetime.now(timezone.utc).isoformat(), flush=True)
    print("=" * 72, flush=True)

    conn = init_db()

    print("\n[1/4] CEO / STRATEGY AGENT", flush=True)

    strategy = ollama(
        f"""
You are CloudNova's CEO Strategy Agent.

{PRODUCT}

For today's run define:
- target customer profile
- primary business problem
- qualification criteria

Keep the answer below 250 words.

STRICT RULES:
- Never invent numerical qualification thresholds.
- Never invent transaction volumes, revenue or company size.
- Do not claim PaymentOps guarantees regulatory compliance.
- Do not claim PaymentOps prevents fraud.
- Do not describe PaymentOps as production-proven.
- Use qualitative qualification criteria unless supported by evidence.
""",
        max_tokens=350,
    )

    print(strategy, flush=True)

    print("\n[2/4] REAL WEB RESEARCH AGENT", flush=True)

    search_results = real_web_search()

    print(
        f"\nCollected {len(search_results)} real web results.",
        flush=True,
    )

    verified = extract_verified_leads(search_results)
    new_leads = save_new_leads(conn, verified)

    print(
        f"Verified organizations: {len(verified)}",
        flush=True,
    )
    print(
        f"NEW organizations after deduplication: {len(new_leads)}",
        flush=True,
    )

    for lead in new_leads:
        print("\n--- VERIFIED LEAD ---", flush=True)
        print(f"Company: {lead['company']}", flush=True)
        print(f"Evidence: {lead['source_url']}", flush=True)
        print(f"Why fit: {lead['why_fit']}", flush=True)
        print(f"Target role: {lead['target_role']}", flush=True)
        print(f"Confidence: {lead['confidence']}", flush=True)

    print("\n[3/4] OUTREACH DRAFT AGENT", flush=True)

    outreach = create_outreach(new_leads)
    print(outreach, flush=True)

    print("\n[4/4] OPERATIONS / REVIEW AGENT", flush=True)

    review = operations_review(new_leads, outreach)
    print(review, flush=True)

    total = conn.execute(
        "SELECT COUNT(*) FROM leads"
    ).fetchone()[0]

    print("\n" + "=" * 72, flush=True)
    print(f"TOTAL UNIQUE LEADS IN MEMORY: {total}", flush=True)
    print("NO EMAILS WERE SENT", flush=True)
    print("WORKFORCE RUN COMPLETE", flush=True)
    print("=" * 72, flush=True)

    conn.close()


if __name__ == "__main__":
    main()


