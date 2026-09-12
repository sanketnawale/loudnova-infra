import json
import os
import urllib.request
from datetime import datetime, timezone

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://ollama:11434/api/generate"
)

MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:3b"
)

PRODUCT = os.getenv(
    "PRODUCT_CONTEXT",
    """
CloudNova builds B2B technology products.

Current focus:
PaymentOps — an ISO 20022 payment validation and repair platform
for banks, payment service providers, fintechs and financial institutions.

The purpose of this run is business-development planning only.
Do not claim that emails have been sent.
Do not invent verified customer contact details.
"""
)


def ask_agent(role, instructions, context=""):
    prompt = f"""
You are the {role} in CloudNova's AI workforce.

PRODUCT CONTEXT:
{PRODUCT}

TASK:
{instructions}

CONTEXT FROM PREVIOUS AGENTS:
{context}

Rules:
- Be concise and practical.
- Do not fabricate verified facts or contact information.
- Clearly distinguish suggestions from verified information.
- Do not claim to have sent emails or contacted anyone.
"""

    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 4096,
            "num_predict": 400,
            "temperature": 0.3
        }
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=300) as response:
        result = json.loads(response.read().decode())

    return result["response"].strip()


print("=" * 70)
print("CLOUDNOVA AI WORKFORCE RUN")
print(datetime.now(timezone.utc).isoformat())
print("=" * 70)


print("\n[1/4] CEO / STRATEGY AGENT")

ceo = ask_agent(
    "CEO and Business Strategist",
    """
Define today's business-development mission for PaymentOps.

Provide:
1. ideal customer profile,
2. three target customer categories,
3. the problem we should lead with,
4. what the Research Agent should investigate.
"""
)

print(ceo)


print("\n[2/4] BUSINESS RESEARCH AGENT")

research = ask_agent(
    "B2B Market Research Agent",
    """
Using the CEO strategy below, create a research plan.

Do NOT invent company contacts.

Provide:
1. what types of organizations to search for,
2. decision-maker job titles,
3. qualification signals,
4. disqualification signals,
5. five example search queries that could later be used by a web-research tool.
""",
    ceo
)

print(research)


print("\n[3/4] OUTREACH AGENT")

outreach = ask_agent(
    "B2B Outreach Specialist",
    """
Create one reusable outreach email framework based on the CEO strategy
and Research Agent findings.

It must:
- sound professional rather than spammy,
- be suitable for a bank or fintech decision maker,
- avoid unsupported claims,
- ask for a short discovery conversation.

DO NOT send anything.
""",
    ceo + "\n\nRESEARCH:\n" + research
)

print(outreach)


print("\n[4/4] OPERATIONS / REVIEW AGENT")

operations = ask_agent(
    "Business Operations and Quality Review Agent",
    """
Review everything produced by the team.

Return:
1. PASS or NEEDS REVISION,
2. strongest part of the plan,
3. risks or unsupported assumptions,
4. actions requiring human approval,
5. recommended next action for the next AI workforce run.
""",
    (
        "CEO:\n" + ceo +
        "\n\nRESEARCH:\n" + research +
        "\n\nOUTREACH:\n" + outreach
    )
)

print(operations)

print("\n" + "=" * 70)
print("WORKFORCE RUN COMPLETE")
print("=" * 70)
