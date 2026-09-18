import ipaddress
import json
import os
import re
import smtplib
import socket
import sqlite3
import ssl
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

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
    "server376.web-hosting.com",
)

SMTP_PORT = _env_port(
    "SMTP_PORT",
    587,
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


REPORT_TIMEZONE = os.getenv(
    "REPORT_TIMEZONE",
    "Europe/Rome",
)


def rome_now():
    try:
        return datetime.now(
            ZoneInfo(REPORT_TIMEZONE)
        )
    except Exception:
        return datetime.now(timezone.utc)


def rome_timestamp():
    return rome_now().strftime(
        "%Y-%m-%d %H:%M"
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

The current implementation is an ISO 20022 pacs.008 vertical slice with
validation and repair-related functionality. It is not production-proven.

Prefer factual language such as:
"CloudNova PaymentOps is an early-stage platform exploring ways to
support ISO 20022 payment validation, analysis and repair workflows."
Never write "ensuring compliance with regulatory standards".

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


RESEARCH_MISSIONS = {
    7: {
        "name": "Banks / ISO 20022",
        "categories": [
            "commercial banks",
            "challenger banks",
            "transaction banking",
            "corporate banking",
        ],
        "geographies": [],
        "existing_lead_limit": 0,
        "queries": [
            '"ISO 20022" commercial bank migration',
            '"ISO 20022" transaction banking readiness',
            '"ISO 20022" corporate banking payments',
            "challenger bank ISO 20022 payment modernization",
            "bank payment modernization ISO 20022",
            '"ISO 20022" readiness page bank',
        ],
        "instructions": (
            "Focus on commercial banks, challenger banks, transaction "
            "banking and corporate banking teams with first-party "
            "evidence of ISO 20022 migration or payment modernization."
        ),
    },
    9: {
        "name": "PSP / Payment Processors",
        "categories": [
            "payment service providers",
            "payment processors",
            "payment infrastructure companies",
        ],
        "geographies": [],
        "existing_lead_limit": 0,
        "queries": [
            '"ISO 20022" payment service provider',
            '"ISO 20022" payment processor',
            "payment operations modernization ISO 20022",
            '"ISO 20022" payment infrastructure company',
            "payment service provider ISO 20022 readiness",
            '"ISO 20022" payment processing platform',
        ],
        "instructions": (
            "Focus on payment service providers and processors that are "
            "potential BUYERS of PaymentOps, not competing payment "
            "software vendors."
        ),
    },
    11: {
        "name": "Fintech",
        "categories": [
            "commercial fintechs",
            "B2B payment fintechs",
            "treasury and payment platforms",
            "cross-border payment companies",
        ],
        "geographies": [],
        "existing_lead_limit": 0,
        "queries": [
            '"ISO 20022" fintech payments',
            "B2B payment fintech ISO 20022",
            "cross-border payments ISO 20022 fintech",
            "treasury payment platform ISO 20022",
            "fintech payment modernization ISO 20022",
            '"ISO 20022" payment platform readiness',
        ],
        "instructions": (
            "Focus on commercial fintechs and payment platforms publicly "
            "discussing ISO 20022, treasury or cross-border payments."
        ),
    },
    13: {
        "name": "Europe Research",
        "categories": [
            "commercial banks",
            "payment service providers",
            "fintechs",
            "financial institutions",
        ],
        "geographies": [
            "Italy",
            "Germany",
            "France",
            "Spain",
            "Netherlands",
            "United Kingdom",
        ],
        "existing_lead_limit": 0,
        "queries": [
            '"ISO 20022" Italy bank payment modernization',
            '"ISO 20022" Germany payment modernization',
            '"ISO 20022" France payment service provider',
            '"ISO 20022" Spain bank payments',
            '"ISO 20022" Netherlands payments modernization',
            '"ISO 20022" United Kingdom bank payments',
        ],
        "instructions": (
            "Focus on commercial organizations in Italy, Germany, France, "
            "Spain, the Netherlands and the UK with first-party payment "
            "modernization or ISO 20022 evidence."
        ),
    },
    15: {
        "name": "Middle East Research",
        "categories": [
            "commercial banks",
            "fintechs",
            "payment service providers",
        ],
        "geographies": [
            "Saudi Arabia",
            "United Arab Emirates",
        ],
        "existing_lead_limit": 0,
        "queries": [
            '"ISO 20022" Saudi Arabia bank payments',
            '"ISO 20022" UAE bank payments',
            '"ISO 20022" Saudi fintech payments',
            '"ISO 20022" UAE payment service provider',
            "payment modernization ISO 20022 Middle East",
            '"ISO 20022" Gulf payment modernization',
        ],
        "instructions": (
            "Focus on commercial banks, fintechs and PSPs in Saudi Arabia "
            "and the UAE with first-party ISO 20022 or payment "
            "modernization evidence."
        ),
    },
    17: {
        "name": "Deep Verification / Enrichment",
        "categories": [
            "existing HUMAN_REVIEW_REQUIRED leads",
        ],
        "geographies": [],
        "existing_lead_limit": 5,
        "queries": [
            "ISO 20022 payment modernization official site",
            "ISO 20022 readiness first-party evidence",
            "payment operations modernization ISO 20022",
        ],
        "instructions": (
            "Focus primarily on previously discovered leads. Search the "
            "company's official website, find stronger first-party "
            "evidence, verify whether it is a potential buyer, identify a "
            "plausible target department or role and improve why_fit. "
            "Do NOT invent people or job titles."
        ),
    },
    19: {
        "name": "Final Discovery + Review",
        "categories": [
            "additional commercial prospects",
            "strongest leads from the day",
        ],
        "geographies": [],
        "existing_lead_limit": 3,
        "queries": [
            '"ISO 20022" bank payments modernization',
            '"ISO 20022" payment service provider modernization',
            '"ISO 20022" fintech payment platform',
            "payment operations modernization ISO 20022",
            '"ISO 20022" payment validation enterprise',
        ],
        "instructions": (
            "Look for additional commercial prospects missed earlier, "
            "revisit the strongest leads from the day, verify evidence, "
            "reject weak prospects and improve draft quality. Identify "
            "leads that deserve human attention."
        ),
    },
}


def get_research_mission(now=None):
    if now is None:
        now = rome_now()

    hour = now.hour
    hours = sorted(RESEARCH_MISSIONS)

    selected = hours[0]

    for candidate in hours:
        if hour >= candidate:
            selected = candidate

    mission = dict(RESEARCH_MISSIONS[selected])
    mission["hour"] = hour

    return mission


ALLOWED_ORGANIZATION_TYPES = {
    "BANK",
    "PSP",
    "FINTECH",
    "FINANCIAL_INSTITUTION",
}


BANNED_ORGANIZATION_NAMES = {
    "example bank",
    "fakecorp",
    "federal reserve financial services",
    "federal reserve bank",
    "federal reserve",
    "fedpayments improvement",
    "fedpaymentsimprovement",
    "gsdcouncil",
    "gsd council",
    "swift",
    "swift community",
    "iso",
    "iso 20022",
    "iso20022",
    "bank for international settlements",
    "european central bank",
    "european payments council",
    "world bank",
    "international monetary fund",
    "bank of england",
    "sepa",
    "european payments initiative",
}


BANNED_DOMAIN_PATTERNS = {
    "federalreserve.gov",
    "frbservices.org",
    "fedpaymentsimprovement.org",
    "minneapolisfed.org",
    "gsdcouncil.org",
    "gsdso.org",
    "swift.com",
    "iso.org",
    "iso20022.org",
    "six-group.com",
}


BANNED_TITLE_OR_SNIPPET_PATTERNS = {
    "federal reserve financial services",
    "fedpayments improvement",
    "gsdcouncil",
    "gsd council",
}


BANNED_DOMAIN_SUFFIXES = (
    ".gov",
    ".gov.uk",
    ".mil",
    ".edu",
    ".edu.au",
    ".ac.uk",
    ".ac.jp",
    ".ac.nz",
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
    "iso20022.org",
    "swift.com",
    "wikipedia.org",
    "university",
    ".ac.",
}


GENERIC_NAME_TOKENS = {
    "the", "and", "of", "for",
    "bank", "banking",
    "financial", "finance",
    "group", "holding", "holdings",
    "services", "service",
    "payments", "payment",
    "international", "global", "national",
    "corporation", "corp", "company", "co",
    "limited", "inc", "llc", "plc", "ltd",
    "technology", "technologies", "tech",
    "systems", "system",
    "ag", "sa", "nv", "se",
}


ACRONYM_STOPWORDS = {
    "the", "and", "of", "for",
}


MULTI_PART_TLDS = {
    "co.uk", "org.uk", "gov.uk", "ac.uk", "me.uk", "ltd.uk", "plc.uk",
    "co.nz", "org.nz", "net.nz", "govt.nz", "ac.nz",
    "com.au", "net.au", "org.au", "edu.au", "gov.au",
    "co.jp", "or.jp", "ne.jp", "ac.jp",
    "com.br", "com.cn", "com.hk", "com.sg", "com.my", "com.tr",
    "com.mx", "com.ar", "com.co", "com.pe", "com.tw", "com.ph",
    "co.in", "co.kr", "co.za", "co.il", "co.id", "co.th",
    "com.sa", "com.ae", "com.qa", "com.kw", "com.eg",
    "co.at", "or.at", "com.pl", "com.es", "com.it", "com.pt",
    "com.ua", "com.ru", "co.ma", "com.ng", "com.pk", "com.bd",
}


LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "llp", "lp", "plc", "ltd", "limited",
    "corp", "corporation", "co", "company", "gmbh", "ag", "sa", "sarl",
    "nv", "bv", "se", "ab", "oy", "oyj", "as", "asa", "aps", "spa",
    "pte", "pty", "srl", "kk", "kg", "ug", "sca", "snc", "sas",
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


def registrable_domain(host):
    host = (host or "").lower().strip(".")

    if not host:
        return ""

    parts = host.split(".")

    if len(parts) <= 2:
        return host

    last_two = ".".join(parts[-2:])

    if last_two in MULTI_PART_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])

    return last_two


def normalize_alnum(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def name_words(name):
    return re.findall(r"[a-z0-9]+", str(name or "").lower())


def name_tokens(name):
    return [
        word
        for word in name_words(name)
        if len(word) >= 3
        and word not in GENERIC_NAME_TOKENS
        and word not in LEGAL_SUFFIXES
    ]


def name_acronym(name):
    return "".join(
        word[0]
        for word in name_words(name)
        if word not in ACRONYM_STOPWORDS
    )


def name_variants(name):
    words = name_words(name)
    non_stop = [w for w in words if w not in ACRONYM_STOPWORDS]
    significant = name_tokens(name)

    variants = {
        normalize_alnum(name),
        "".join(non_stop),
        "".join(significant),
    }

    return {v for v in variants if len(v) >= 3}


def company_domain_match(name, url):
    host = domain_from_url(url)

    if not host:
        return False

    root = registrable_domain(host)
    root_label = root.split(".")[0] if root else ""
    root_alnum = normalize_alnum(root_label)
    normalized = normalize_alnum(name)
    distinctive = name_tokens(name)
    acronym = name_acronym(name)

    # 1) strong normalized full-name match (the whole name equals the domain label)
    if len(normalized) >= 4 and normalized == root_alnum:
        return True

    # 2) strong full-name / concatenated distinctive-token match.
    #    Generic business words are excluded by name_tokens, so generic tokens alone
    #    can never establish a first-party match here.
    if distinctive:
        concatenated = "".join(distinctive)

        if len(concatenated) >= 4 and concatenated in host:
            return True

        for token in distinctive:
            if len(token) >= 3 and token in host:
                return True

    # 3) acronym match, or a justified acronym / domain-prefix relationship
    if len(acronym) >= 3:
        if acronym in host:
            return True

        if root_label and (
            root_label.startswith(acronym)
            or acronym.startswith(root_label)
        ):
            return True

    return False


def name_appears_in_text(name, text):
    hay = normalize_alnum(text)

    if not hay:
        return False

    normalized = normalize_alnum(name)

    if normalized and normalized in hay:
        return True

    tokens = name_tokens(name)
    acronym = name_acronym(name)

    if len(acronym) >= 3 and acronym in hay:
        return True

    if not tokens:
        return False

    present = sum(1 for token in tokens if token in hay)

    if present == len(tokens):
        return True

    if present >= 1 and len(tokens) == 1:
        return True

    if present >= max(1, (len(tokens) + 1) // 2):
        return True

    return False


def name_matches_banned(name):
    words = " " + " ".join(name_words(name)) + " "

    for banned in BANNED_ORGANIZATION_NAMES:
        if " " + banned + " " in words:
            return True

    return False


def evidence_is_first_party(name, source):
    url = source.get("url", "") if isinstance(source, dict) else str(source or "")

    return company_domain_match(name, url)


def is_disallowed_prospect(name, source):
    url = source.get("url", "") if isinstance(source, dict) else str(source or "")
    domain = domain_from_url(url)

    if name_matches_banned(name):
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
    conn.row_factory = sqlite3.Row

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

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            mission TEXT NOT NULL,
            search_count INTEGER NOT NULL,
            results_count INTEGER NOT NULL,
            qualified_count INTEGER NOT NULL,
            new_leads_count INTEGER NOT NULL,
            enriched_count INTEGER NOT NULL,
            rejected_count INTEGER NOT NULL,
            run_status TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lead_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_domain TEXT NOT NULL,
            evidence_summary TEXT,
            first_party INTEGER NOT NULL,
            discovered_at TEXT NOT NULL,
            UNIQUE (company_key, source_url)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lead_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_key TEXT NOT NULL,
            contact_name TEXT,
            contact_role TEXT,
            contact_email TEXT,
            contact_url TEXT,
            contact_type TEXT,
            source_url TEXT,
            confidence TEXT,
            verified_at TEXT,
            first_party INTEGER NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_contacts_email
        ON lead_contacts (company_key, contact_email)
        WHERE contact_email IS NOT NULL
        """
    )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_contacts_url
        ON lead_contacts (company_key, contact_url)
        WHERE contact_url IS NOT NULL
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            mission TEXT NOT NULL,
            query TEXT NOT NULL,
            normalized_query TEXT NOT NULL,
            results_count INTEGER NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_search_history_normalized
        ON search_history (normalized_query)
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            run_timestamp TEXT NOT NULL,
            mission TEXT NOT NULL,
            query TEXT,
            result_index INTEGER,
            title TEXT,
            url TEXT,
            domain TEXT,
            snippet TEXT,
            decision TEXT,
            decision_reason TEXT,
            company_key TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_research_results_run
        ON research_results (run_id)
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


def revalidate_lead(company, source_url, organization_type=None):
    """Re-check a persisted lead against the CURRENT rules.

    Used before any EXISTING lead is selected for follow-up research, contact
    discovery, enrichment or outreach. Historical rows are never deleted; a lead
    that no longer qualifies is skipped and reported as LEGACY_REJECTED.
    """
    source = {
        "url": source_url or "",
        "title": company or "",
        "snippet": "",
    }

    if name_matches_banned(company):
        return False, "legacy_banned_organization"

    disallowed, reason = is_disallowed_prospect(company, source)

    if disallowed:
        return False, "legacy_" + re.sub(
            r"[^a-z0-9]+",
            "_",
            reason.lower(),
        ).strip("_")

    if not company_domain_match(company, source_url):
        return False, "legacy_not_first_party"

    if organization_type:
        if str(organization_type).upper() not in ALLOWED_ORGANIZATION_TYPES:
            return False, "legacy_invalid_type"

    return True, "ok"


def existing_lead_queries(conn, limit=5):
    rows = conn.execute(
        """
        SELECT company, source_url
        FROM leads
        WHERE status = 'HUMAN_REVIEW_REQUIRED'
        ORDER BY confidence DESC, first_seen ASC
        """
    ).fetchall()

    queries = []

    for row in rows:
        name = str(row["company"]).strip()

        if not name:
            continue

        if not revalidate_lead(name, row["source_url"])[0]:
            continue

        queries.append(f'"{name}" ISO 20022')

        if len(queries) >= limit:
            break

    return queries


def real_web_search(
    queries,
    max_results_per_query=5,
    max_total=24,
    on_progress=None,
):
    all_results = []
    seen_urls = set()
    searches_performed = 0

    ddgs = DDGS(
        timeout=20,
    )

    for query in queries:
        print(
            f"\nWEB SEARCH: {query}",
            flush=True,
        )

        searches_performed += 1

        try:
            results = ddgs.text(
                query,
                region="wt-wt",
                safesearch="moderate",
                max_results=max_results_per_query,
            )

        except Exception as exc:
            print(
                f"Search failed: {exc}",
                flush=True,
            )
            results = []

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
                    "query": query,
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

            if len(all_results) >= max_total:
                break

        if on_progress is not None:
            try:
                on_progress(
                    searches_performed,
                    len(queries),
                    len(all_results),
                )
            except Exception:
                pass

        if len(all_results) >= max_total:
            break

    return all_results, searches_performed


def extract_verified_leads(
    conn,
    run_id,
    run_time,
    results,
    mission,
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

RESEARCH MISSION:
- Name: {mission.get("name", "General Research")}
- Target categories: {", ".join(mission.get("categories", [])) or "commercial payment organizations"}
- Geographies: {", ".join(mission.get("geographies", [])) or "worldwide"}
- Instructions: {mission.get("instructions", "")}

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
- Do NOT treat Swift, ISO organizations, regulators, central banks, or
  government infrastructure as prospects.
- Quality matters more than quantity: only return strong candidates.

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
    decisions = {}

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

        if not name_appears_in_text(name, source_text) and not company_domain_match(name, source["url"]):
            print(
                (
                    "REJECT HALLUCINATED COMPANY: "
                    f"{name}"
                ),
                flush=True,
            )
            decisions[idx] = ("REJECTED", "hallucinated_company", None)
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
            decisions[idx] = ("REJECTED", rejection_reason, None)
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
            decisions[idx] = ("REJECTED", "third_party", None)
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
            decisions[idx] = ("REJECTED", "invalid_type", None)
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
            decisions[idx] = ("REJECTED", "low_confidence", None)
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

        decisions[idx] = (
            "QUALIFIED",
            "qualified",
            company_key(name),
        )

    for index, item in enumerate(results):
        decision, reason, key = decisions.get(
            index,
            ("INSPECTED", "", None),
        )

        try:
            record_research_result(
                conn,
                run_id,
                run_time,
                mission.get("name", ""),
                {"id": index, **item},
                decision,
                reason,
                key,
            )
        except Exception:
            pass

    try:
        conn.commit()
    except Exception:
        pass

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


def evidence_is_new(conn, key, source_url):
    row = conn.execute(
        """
        SELECT 1
        FROM lead_evidence
        WHERE company_key = ?
          AND source_url = ?
        """,
        (key, source_url),
    ).fetchone()

    return row is None


def record_evidence(
    conn,
    key,
    source_url,
    evidence_summary,
):
    conn.execute(
        """
        INSERT OR IGNORE INTO lead_evidence (
            company_key,
            source_url,
            source_domain,
            evidence_summary,
            first_party,
            discovered_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            key,
            source_url,
            domain_from_url(source_url),
            str(evidence_summary or "")[:700],
            1,
            datetime.now(
                timezone.utc
            ).isoformat(),
        ),
    )


def save_or_enrich_leads(
    conn,
    leads,
):
    new_leads = []
    enriched_leads = []
    legacy_rejected = []

    for lead in leads:
        key = company_key(
            lead["company"]
        )

        if not key:
            continue

        source_is_new = evidence_is_new(
            conn,
            key,
            lead["source_url"],
        )

        existing = conn.execute(
            """
            SELECT
                company,
                source_url,
                why_fit,
                target_role,
                confidence
            FROM leads
            WHERE company_key = ?
            """,
            (key,),
        ).fetchone()

        if existing is None:
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

            record_evidence(
                conn,
                key,
                lead["source_url"],
                lead["why_fit"],
            )

            new_leads.append(lead)
            continue

        ok, legacy_reason = revalidate_lead(
            existing["company"],
            existing["source_url"],
        )

        if not ok:
            legacy_rejected.append(
                {
                    "company": existing["company"],
                    "reason": legacy_reason,
                    "source_url": existing["source_url"],
                }
            )
            print(
                (
                    "LEGACY_REJECTED: "
                    f"{existing['company']} ({legacy_reason})"
                ),
                flush=True,
            )
            continue

        if not source_is_new:
            print(
                (
                    "SKIP DUPLICATE (known evidence): "
                    f"{lead['company']}"
                ),
                flush=True,
            )
            continue

        old_confidence = int(
            existing["confidence"] or 0
        )
        new_confidence = int(
            lead["confidence"]
        )
        old_why = existing["why_fit"] or ""
        new_why = lead["why_fit"] or ""
        old_role = existing["target_role"] or ""
        new_role = lead["target_role"] or ""

        changes = []

        if len(new_why) > len(old_why):
            changes.append("improved why_fit")

        if new_confidence > old_confidence:
            changes.append(
                f"confidence {old_confidence} -> {new_confidence}"
            )

        if new_role and new_role != old_role:
            changes.append(
                f"target role -> {new_role}"
            )

        if not changes:
            print(
                (
                    "NO ENRICHMENT (no stronger evidence): "
                    f"{lead['company']}"
                ),
                flush=True,
            )
            continue

        conn.execute(
            """
            UPDATE leads
            SET why_fit = ?,
                target_role = ?,
                confidence = ?,
                source_url = ?
            WHERE company_key = ?
            """,
            (
                new_why or old_why,
                new_role or old_role,
                max(old_confidence, new_confidence),
                lead["source_url"],
                key,
            ),
        )

        record_evidence(
            conn,
            key,
            lead["source_url"],
            new_why,
        )

        enriched = dict(lead)
        enriched["what_changed"] = "; ".join(changes)
        enriched_leads.append(enriched)

        print(
            (
                "ENRICHED EXISTING LEAD: "
                f"{lead['company']} "
                f"({enriched['what_changed']})"
            ),
            flush=True,
        )

    conn.commit()

    return new_leads, enriched_leads, legacy_rejected


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
TARGET PERSON:
PUBLIC PROFESSIONAL EMAIL:
CONTACT METHOD:
CONTACT SOURCE:
EVIDENCE USED:
SOURCE URL:
SUBJECT:
EMAIL:

STRICT RULES:

- Produce exactly ONE draft.
- Do not repeat the company.
- Do not output multiple alternatives.
- Maximum 120 words in the EMAIL.
- Use only the supplied evidence and supplied contact data.
- TARGET PERSON must be the supplied verified person's name, or exactly
  "NOT IDENTIFIED". Never put a job title, role or the target role in
  TARGET PERSON.
- PUBLIC PROFESSIONAL EMAIL must be the supplied verified email, or exactly
  "NOT PUBLICLY VERIFIED". Never invent or guess an address.
- CONTACT METHOD must be "Public professional email", "Official contact page"
  or "Professional profile", taken from the supplied contact data.
- The CONTACT SOURCE must come only from the supplied contact data; never
  invent a contact source.
- Never call CloudNova a leader.
- Never claim CloudNova has existing customers.
- Never invent contact names or people.
- Never invent email addresses.
- Never invent metrics.
- Never invent regulatory certifications.
- Never claim guaranteed compliance.
- Never claim "ensuring compliance with regulatory standards".
- Never claim fraud prevention.
- Never claim PaymentOps is production-proven.
- Never claim market leadership.
- Never claim guaranteed cost savings or operational improvements.
- Never imply the recipient already needs or wants PaymentOps.
- Do not claim the company has a problem unless first-party evidence proves it.
- Target roles are role-based only, for example:
  Head of Payments, Head of Payment Operations,
  Payments Technology Lead, Transaction Banking Technology Lead.
- Phrase the message as exploratory business development.
- Open with a concrete observation grounded in the supplied first-party
  evidence, for example:
  "I noticed <Company>'s public material on ISO 20022 readiness and migration."
- Use language such as:
  "We are developing..."
  "We are exploring whether..."
  "Would you be open to a short discovery conversation?"
- Keep the product description close to:
  "CloudNova PaymentOps is an early-stage platform exploring ways to support
  ISO 20022 payment validation, analysis and repair workflows."
- Do NOT use filler or unsupported framing such as:
  "It aligns with the regulatory focus you've highlighted."
  "I am confident we can..."
  "we ensure compliance..."
  "we guarantee compliance..."
  "we prevent fraud..."
  "we are production-proven..."
  "we are market-leading..."
  "we will reduce costs..."
- End with a request for a short discovery conversation.
- Do NOT send anything.
- This draft requires explicit human approval.
"""

    return ollama(
        prompt,
        max_tokens=700,
    )


OUTREACH_FIELD_RE = re.compile(r"^([A-Z][A-Z /]+):\s*(.*)$")


def sanitize_outreach_draft(draft, lead):
    """Force verified-only contact fields; a role is never a person."""
    contact = lead.get("contact") or {}
    email = str(contact.get("contact_email") or "").strip()
    verified_email = email if "@" in email else "NOT PUBLICLY VERIFIED"

    person = str(contact.get("contact_name") or "").strip()

    if not person or person.upper() == "NOT IDENTIFIED":
        person = "NOT IDENTIFIED"

    role = str(
        contact.get("contact_role")
        or lead.get("target_role")
        or "Head of Payments"
    ).strip()

    ctype = str(contact.get("contact_type") or "none").strip()

    if "@" in email:
        method = "Public professional email"
    elif ctype == "contact_page":
        method = "Official contact page"
    elif ctype == "profile":
        method = "Professional profile"
    else:
        method = "Official contact page / professional profile"

    source = contact.get("source_url") or lead.get("source_url") or ""

    fields = {
        "TARGET ROLE": role,
        "TARGET PERSON": person,
        "PUBLIC PROFESSIONAL EMAIL": verified_email,
        "CONTACT METHOD": method,
        "CONTACT SOURCE": source,
    }

    out = []
    seen = set()

    for line in str(draft or "").splitlines():
        match = OUTREACH_FIELD_RE.match(line)

        if match and match.group(1).strip() in fields:
            name = match.group(1).strip()
            out.append(f"{name}: {fields[name]}")
            seen.add(name)
        else:
            out.append(line)

    for name, value in fields.items():
        if name not in seen:
            out.append(f"{name}: {value}")

    return "\n".join(out)


def create_outreach(leads, max_drafts=4):
    leads = deduplicate_leads(
        leads
    )

    drafts = []

    if not leads:
        return drafts

    for lead in leads[:max_drafts]:
        print(
            (
                "Generating exactly one outreach draft for: "
                f"{lead['company']}"
            ),
            flush=True,
        )

        drafts.append(
            {
                "company": lead["company"],
                "draft": sanitize_outreach_draft(
                    create_outreach_for_lead(
                        lead
                    ),
                    lead,
                ),
            }
        )

    return drafts


PROHIBITED_OUTREACH_PHRASES = (
    "guarantee compliance",
    "guarantees compliance",
    "guaranteed compliance",
    "guarantee regulatory compliance",
    "guarantees regulatory compliance",
    "ensure compliance",
    "ensures compliance",
    "ensuring compliance",
    "fraud prevention",
    "fraud-prevention",
    "prevent fraud",
    "prevents fraud",
    "production-proven",
    "production proven",
    "market-leading",
    "market leading",
    "market leader",
    "guaranteed savings",
    "guarantee savings",
    "guaranteed cost savings",
    "guaranteed operational improvements",
)


def find_unsupported_claims(text):
    hay = re.sub(r"\s+", " ", str(text or "").lower())
    found = []

    for phrase in PROHIBITED_OUTREACH_PHRASES:
        if phrase in hay and phrase not in found:
            found.append(phrase)

    return found


def enforce_unsupported_claims(review, unsupported):
    value = "NONE" if not unsupported else "; ".join(sorted(set(unsupported)))
    text = str(review or "")
    pattern = re.compile(
        r"(?im)^(\s*(?:\d+\.\s*)?Unsupported claims found\s*:\s*).*$"
    )

    if pattern.search(text):
        return pattern.sub(lambda match: match.group(1) + value, text)

    return text.rstrip() + f"\n\nUnsupported claims found: {value}"


def operations_review(
    leads,
    outreach,
):
    if not leads:
        return (
            "Candidate leads: 0\n"
            "No per-lead review required."
        )

    unsupported = find_unsupported_claims(outreach)
    unsupported_text = ", ".join(unsupported) if unsupported else "NONE"

    prompt = f"""
You are CloudNova's strict Business Development Quality Gate.
You are the final challenge before human review. Be skeptical.

PRODUCT:
{PRODUCT}

CANDIDATE LEADS:

{json.dumps(leads, ensure_ascii=False, indent=2)}

OUTREACH DRAFTS:

{outreach}

DETERMINISTIC PROHIBITED-PHRASE SCAN OF THE ACTUAL OUTREACH DRAFTS:

{unsupported_text}

Evaluate ONLY the candidate leads listed above.
Do NOT invent leads, do NOT reference "Lead #1" unless it is listed above,
and do NOT invent unsupported-claims findings.

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
- For the section "Unsupported claims found", report EXACTLY the
  deterministic scan above and nothing else. If it is NONE, output exactly
  "Unsupported claims found: NONE".
- Do NOT invent unsupported claims: a prohibited phrase only counts if it
  literally appears in the outreach drafts above.

No email has been sent.
"""

    review = ollama(
        prompt,
        max_tokens=700,
    )

    return enforce_unsupported_claims(review, unsupported)


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
        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=30,
        ) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
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
    max_examples=5,
):
    lines = ["REJECTED CANDIDATES"]

    for reason in REJECTION_REASON_KEYS:
        lines.append(
            f"- {REJECTION_REASON_LABELS[reason]}: "
            f"{rejection_stats.get(reason, 0)}"
        )

    examples = []

    for reason in REJECTION_REASON_KEYS:
        bucket = rejection_examples.get(reason) or []

        for item in bucket:
            if len(examples) >= max_examples:
                break

            examples.append(
                f"- {REJECTION_REASON_LABELS[reason]}: "
                f"{item}"
            )

        if len(examples) >= max_examples:
            break

    if examples:
        lines.append("Examples:")
        lines.extend(examples)

    return "\n".join(lines)


def build_daily_report(
    run_time,
    mission_name,
    run_status,
    search_count,
    results_count,
    qualified_count,
    new_leads,
    enriched_leads,
    rejection_stats,
    rejection_examples,
    outreach_drafts,
    review,
    total,
    review_count,
    contacts=None,
    new_companies=None,
    new_contacts_count=0,
    new_angles=None,
    legacy_rejected=None,
):
    contacts = contacts or []
    new_companies = new_companies or []
    new_angles = new_angles or []
    legacy_rejected = legacy_rejected or []

    lines = [
        "CLOUDNOVA BUSINESS WORKFORCE",
        f"RUN TIME: {run_time} Europe/Rome",
        f"MISSION: {mission_name}",
        f"RUN STATUS: {run_status}",
        "",
        "SEARCH SUMMARY",
        f"- searches performed: {search_count}",
        f"- results inspected: {results_count}",
        f"- candidates evaluated: {qualified_count}",
        f"- new search angles used: {len(new_angles)}",
    ]

    if new_angles:
        for angle in new_angles[:8]:
            lines.append(f"  - {angle}")


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
    lines.append("EXISTING COMPANIES ENRICHED")

    if enriched_leads:
        for lead in enriched_leads:
            lines.append("")
            lines.append(
                f"Company: {lead.get('company', '')}"
            )
            lines.append(
                f"New evidence: {lead.get('why_fit', '')}"
            )
            lines.append(
                f"Source URL: {lead.get('source_url', '')}"
            )
            lines.append(
                "What changed: "
                + str(lead.get("what_changed", ""))
            )
    else:
        lines.append(
            "No existing leads were materially enriched "
            "in this run."
        )

    lines.append("")
    lines.append("NEW COMPANIES DISCOVERED")

    if new_companies:
        for name in new_companies:
            lines.append(f"- {name}")
    else:
        lines.append("No new companies discovered in this run.")

    lines.append("")
    lines.append("CONTACTS DISCOVERED")

    if contacts:
        for contact in contacts:
            lines.append("")
            lines.append(str(contact.get("company", "")))
            lines.append(
                "Target role: "
                + str(contact.get("contact_role", ""))
            )
            lines.append(
                "Target person: "
                + str(contact.get("contact_name", "NOT IDENTIFIED"))
            )
            lines.append(
                "Public professional email: "
                + str(contact.get("contact_email", "NOT PUBLICLY VERIFIED"))
            )
            lines.append(
                "Alternative contact: "
                + str(contact.get("contact_url") or "none found")
            )
            lines.append(
                "Source: " + str(contact.get("source_url", ""))
            )
            lines.append(
                "Confidence: " + str(contact.get("confidence", "LOW"))
            )
    else:
        lines.append("No contacts discovered in this run.")

    lines.append("")
    lines.append("LEGACY LEADS SKIPPED")

    if legacy_rejected:
        for item in legacy_rejected:
            lines.append(
                f"- {item.get('company', '')} ({item.get('reason', '')})"
            )
    else:
        lines.append("No legacy leads required skipping in this run.")

    lines.append("")
    lines.append("OUTREACH DRAFTS")

    if outreach_drafts:
        for item in outreach_drafts:
            lines.append("")
            lines.append(
                f"--- DRAFT: {item['company']} ---"
            )
            lines.append(str(item["draft"]))
    else:
        lines.append("No outreach drafts generated.")

    lines.append("")
    lines.append(
        build_rejection_summary(
            rejection_stats,
            rejection_examples,
        )
    )

    lines.append("")
    lines.append("OPERATIONS REVIEW")
    lines.append(
        review
        or "No operations review available."
    )

    lines.append("")
    lines.append("DATABASE SUMMARY")
    lines.append(f"- total unique leads: {total}")
    lines.append(
        "- total HUMAN_REVIEW_REQUIRED: "
        f"{review_count}"
    )
    lines.append(f"- new this run: {len(new_leads)}")
    lines.append(
        f"- enriched this run: {len(enriched_leads)}"
    )
    lines.append(
        f"- new contacts this run: {new_contacts_count}"
    )

    lines.append("")
    lines.append("SAFETY")
    lines.append(
        "NO EXTERNAL PROSPECT EMAILS WERE SENT."
    )
    lines.append(
        "ALL PROSPECT OUTREACH REQUIRES HUMAN APPROVAL."
    )

    return "\n".join(lines)


WORKFORCE_STATUS_PATH = os.getenv(
    "WORKFORCE_STATUS_FILE",
    "/data/workforce-status.json",
)

STATUS_MAX_ACTIVITY = 50

STATUS_AGENT_DEFS = (
    ("nova", "NOVA", "CEO / Strategy"),
    ("scout", "SCOUT", "Web Research"),
    ("verify", "VERIFY", "Lead Verification"),
    ("atlas", "ATLAS", "Lead Enrichment"),
    ("piper", "PIPER", "Outreach Draft"),
    ("sentinel", "SENTINEL", "Operations Review"),
)


def _status_safety():
    return {
        "prospectEmailsSent": 0,
        "humanApprovalRequired": True,
        "prospectOutreach": "DRAFT_ONLY",
        "reportRecipient": "operator-only",
    }


def _atomic_write_json(path, payload):
    directory = os.path.dirname(path) or "."

    os.makedirs(
        directory,
        exist_ok=True,
    )

    fd, temp_path = tempfile.mkstemp(
        prefix=".workforce-status-",
        suffix=".tmp",
        dir=directory,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
            )
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_path, path)

    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def next_run_iso(now=None):
    now = now or rome_now()
    current = now.hour * 60 + now.minute
    hours = sorted(RESEARCH_MISSIONS)

    for hour in hours:
        at = hour * 60 + 30
        if at > current:
            return (
                now + timedelta(minutes=at - current)
            ).isoformat()

    first = hours[0]
    delta = (24 * 60 - current) + first * 60 + 30

    return (now + timedelta(minutes=delta)).isoformat()


class WorkforceStatus:
    def __init__(self, mission_name, run_time, path=None):
        self.path = path or WORKFORCE_STATUS_PATH
        self.run_id = rome_now().strftime("%Y%m%d-%H%M")
        self.mission = mission_name
        self.run_time = run_time
        self.workforce_status = "RUNNING"
        self.current_agent = None
        self.metrics = {
            "searches": 0,
            "searchesPlanned": 0,
            "resultsInspected": 0,
            "candidatesEvaluated": 0,
            "newLeads": 0,
            "enrichedLeads": 0,
            "rejectedCandidates": 0,
            "reviewRequired": 0,
            "newContacts": 0,
            "newCompanies": 0,
        }
        self.activity = []
        self.agents = {
            agent_id: {
                "id": agent_id,
                "name": name,
                "role": role,
                "state": "IDLE",
            }
            for agent_id, name, role in STATUS_AGENT_DEFS
        }

    def _stamp(self):
        return rome_now().strftime("%H:%M:%S")

    def log(self, agent_name, message):
        self.activity.insert(
            0,
            {
                "time": self._stamp(),
                "agent": agent_name,
                "message": str(message),
            },
        )
        del self.activity[STATUS_MAX_ACTIVITY:]

    def set_agent(self, agent_id, state, task=None, progress=None):
        agent = self.agents.get(agent_id)

        if agent is None:
            return

        agent["state"] = state

        if task is not None:
            agent["task"] = str(task)

        if progress is not None:
            agent["progress"] = str(progress)

        if state == "WORKING":
            self.current_agent = agent_id

    def set_metric(self, key, value):
        if key not in self.metrics:
            return

        try:
            self.metrics[key] = int(value)
        except (TypeError, ValueError):
            self.metrics[key] = 0

    def snapshot(self):
        return {
            "visualization": True,
            "company": "CloudNova",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "workforce": {
                "status": self.workforce_status,
                "runId": self.run_id,
                "runTime": self.run_time,
                "mission": self.mission,
                "nextRun": next_run_iso(),
            },
            "agents": [
                dict(self.agents[agent_id])
                for agent_id, _name, _role in STATUS_AGENT_DEFS
            ],
            "metrics": dict(self.metrics),
            "activity": list(self.activity),
            "safety": _status_safety(),
        }

    def write(self):
        try:
            _atomic_write_json(
                self.path,
                self.snapshot(),
            )
        except Exception as exc:
            print(
                "WORKFORCE STATUS WRITE FAILED: "
                + safe_error(str(exc)),
                flush=True,
            )

    def complete(self):
        for agent in self.agents.values():
            if agent["state"] == "WORKING":
                agent["state"] = "COMPLETE"

        self.workforce_status = "COMPLETE"
        self.write()

    def fail(self):
        current = self.agents.get(self.current_agent)

        if current is not None and current["state"] == "WORKING":
            current["state"] = "ERROR"

        self.workforce_status = "ERROR"
        self.write()


TARGET_ROLES = (
    "Head of Payments",
    "Head of Payment Operations",
    "Payments Technology Lead",
    "Transaction Banking Technology Lead",
    "ISO 20022 Programme Lead",
    "Payment Architecture Lead",
    "Head of Transaction Banking",
    "Global Payments Lead",
)

CONTACT_QUERY_TEMPLATES = (
    '"{company}" payments contact',
    '"{company}" head of payments',
    '"{company}" leadership team payments',
)

EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)

PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk",
    "hotmail.com", "outlook.com", "live.com", "msn.com",
    "icloud.com", "me.com", "aol.com", "protonmail.com",
    "proton.me", "gmx.com", "gmx.net", "mail.com",
    "yandex.com", "qq.com", "163.com", "126.com",
    "zoho.com", "tutanota.com",
}

ROLE_MAILBOX_PREFIXES = {
    "payments", "payment", "iso20022", "iso", "iso-20022",
    "treasury", "operations", "transaction", "corporate",
    "business", "sales", "trade",
}

GENERIC_MAILBOX_PREFIXES = {
    "info", "contact", "enquiries", "enquiry", "inquiries",
    "inquiry", "hello", "team", "general", "office",
    "press", "media", "investor", "investors", "careers", "jobs",
}

# footer/legal/privacy/security/webmaster/cookie/support style addresses are
# not useful prospecting routes and are ignored unless they are the only route.
IGNORED_MAILBOX_PREFIXES = {
    "privacy", "legal", "security", "webmaster", "cookie", "cookies",
    "support", "abuse", "postmaster", "noreply", "no-reply", "donotreply",
    "dmca", "unsubscribe", "complaints", "gdpr", "dpo", "dataprotection",
    "dataprivacy", "helpdesk", "help",
}

MAX_NEW_CONTACTS_PER_COMPANY = 3

CONTACT_TYPE_RANK = {
    "role_mailbox": 4,
    "work_email": 3,
    "contact_page": 2,
    "profile": 1,
}

BAD_EMAIL_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".svg", ".css", ".js", ".ico",
)

CONTACT_LINK_RE = re.compile(
    r"(contact|contacts|get-in-touch|enquir|inquir|team|leadership|"
    r"management|about|press|media|investor)",
    re.IGNORECASE,
)

FETCH_USER_AGENT = (
    "CloudNovaResearchBot/1.0 (+https://cloudnova.tech; read-only research)"
)

MAX_FETCH_BYTES = 200000


def _host_is_public(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False

    if not infos:
        return False

    for info in infos:
        addr = info[4][0]

        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False

    return True


def safe_fetch(url, max_bytes=MAX_FETCH_BYTES, timeout=12):
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except ValueError:
        return None

    if parsed.scheme not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()

    if not host or host in ("localhost", "localhost.localdomain"):
        return None

    try:
        port = parsed.port
    except ValueError:
        return None

    if port is not None and port not in (80, 443):
        return None

    if not _host_is_public(host):
        return None

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": FETCH_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            content_type = (
                response.headers.get("Content-Type") or ""
            ).lower()

            if content_type and not (
                "text/html" in content_type
                or "text/plain" in content_type
                or "application/xhtml" in content_type
            ):
                return None

            raw = response.read(max_bytes)

    except Exception:
        return None

    return raw.decode("utf-8", errors="replace")


def html_to_text(html):
    text = re.sub(r"(?is)<script.*?</script>", " ", html or "")
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _mailbox_tokens(local):
    return [
        token
        for token in re.split(r"[^a-z0-9]+", (local or "").lower())
        if token
    ]


def is_role_mailbox(local):
    tokens = _mailbox_tokens(local)

    if not tokens:
        return False

    first = tokens[0]

    return first in ROLE_MAILBOX_PREFIXES or first.startswith(
        ("payments", "iso", "treasury", "operations", "transaction")
    )


def is_ignored_mailbox(local):
    return any(
        token in IGNORED_MAILBOX_PREFIXES
        for token in _mailbox_tokens(local)
    )


def is_generic_mailbox(local):
    tokens = _mailbox_tokens(local)

    return bool(tokens) and tokens[0] in GENERIC_MAILBOX_PREFIXES


def contact_rank(contact):
    return CONTACT_TYPE_RANK.get(contact.get("contact_type"), 0)


def emails_on_company_domain(text, company_domain):
    found = []

    for match in EMAIL_RE.findall(text or ""):
        email = match.strip().strip(".").lower()
        local, _, host = email.partition("@")

        if not local or not host:
            continue

        if host.endswith(BAD_EMAIL_SUFFIXES):
            continue

        if host in PERSONAL_EMAIL_DOMAINS:
            continue

        if registrable_domain(host) != company_domain:
            continue

        if email not in found:
            found.append(email)

    return found


def extract_contact_links(html, base_url):
    links = []

    for href in re.findall(
        r'href=["\']([^"\']+)["\']',
        html or "",
        re.IGNORECASE,
    ):
        full = urllib.parse.urljoin(base_url, href)

        if not full.startswith(("http://", "https://")):
            continue

        if CONTACT_LINK_RE.search(full) and full not in links:
            links.append(full)

    return links[:8]


def choose_target_role(lead, page_text):
    hay = (page_text or "").lower()

    for role in TARGET_ROLES:
        if role.lower() in hay:
            return role

    return lead.get("target_role") or "Head of Payments"


def contacts_from_first_party_page(
    company,
    page_url,
    page_html,
    company_domain,
):
    contacts = []
    text = html_to_text(page_html)

    for email in emails_on_company_domain(page_html, company_domain):
        local = email.split("@")[0]

        if is_ignored_mailbox(local):
            continue

        contacts.append(
            {
                "contact_name": "",
                "contact_role": "",
                "contact_email": email,
                "contact_url": page_url,
                "contact_type": (
                    "role_mailbox" if is_role_mailbox(local) else "work_email"
                ),
                "source_url": page_url,
                "confidence": "HIGH",
                "first_party": 1,
                "page_text": text,
            }
        )

    for link in extract_contact_links(page_html, page_url):
        if registrable_domain(domain_from_url(link)) == company_domain:
            contacts.append(
                {
                    "contact_name": "",
                    "contact_role": "",
                    "contact_email": None,
                    "contact_url": link,
                    "contact_type": "contact_page",
                    "source_url": page_url,
                    "confidence": "MEDIUM",
                    "first_party": 1,
                    "page_text": text,
                }
            )

    return contacts


def discover_contacts_for_lead(company, lead, fetch_budget):
    company_domain = registrable_domain(
        domain_from_url(lead.get("source_url", ""))
    )
    contacts = []
    fetches = 0

    def add_from_url(url):
        nonlocal fetches

        if fetches >= fetch_budget:
            return

        html = safe_fetch(url)
        fetches += 1

        if html:
            contacts.extend(
                contacts_from_first_party_page(
                    company,
                    url,
                    html,
                    company_domain,
                )
            )

    evidence_url = lead.get("source_url", "")

    if evidence_url and company_domain_match(company, evidence_url):
        add_from_url(evidence_url)

    queries = [
        template.format(company=company)
        for template in CONTACT_QUERY_TEMPLATES
    ]

    if company_domain:
        queries.append(f"site:{company_domain} contact")

    seen_urls = set()
    ddgs = None

    try:
        ddgs = DDGS(timeout=20)
    except Exception:
        ddgs = None

    if ddgs is not None:
        for query in queries[:3]:
            try:
                results = ddgs.text(
                    query,
                    region="wt-wt",
                    safesearch="moderate",
                    max_results=4,
                )
            except Exception:
                results = []

            for item in results or []:
                url = item.get("href", "")

                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)

                if not company_domain_match(company, url):
                    continue

                if fetches >= fetch_budget:
                    break

                add_from_url(url)

    if not any(c.get("contact_email") for c in contacts):
        for url in seen_urls:
            if company_domain_match(company, url) and CONTACT_LINK_RE.search(url):
                contacts.append(
                    {
                        "contact_name": "",
                        "contact_role": "",
                        "contact_email": None,
                        "contact_url": url,
                        "contact_type": "contact_page",
                        "source_url": url,
                        "confidence": "MEDIUM",
                        "first_party": 1,
                    }
                )
                break

    if not any(
        c.get("contact_email") or c.get("contact_type") == "contact_page"
        for c in contacts
    ):
        for url in seen_urls:
            if "linkedin.com/company/" in url.lower():
                contacts.append(
                    {
                        "contact_name": "",
                        "contact_role": "",
                        "contact_email": None,
                        "contact_url": url,
                        "contact_type": "profile",
                        "source_url": url,
                        "confidence": "LOW",
                        "first_party": 0,
                    }
                )
                break

    unique = []
    seen = set()

    for contact in contacts:
        key = (contact.get("contact_email"), contact.get("contact_url"))

        if key in seen:
            continue

        seen.add(key)
        unique.append(contact)

    return unique, fetches


CONTACT_CONFIDENCE_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def find_contact(conn, key, contact):
    email = (contact.get("contact_email") or "").lower() or None
    url = contact.get("contact_url") or None

    if email:
        row = conn.execute(
            """
            SELECT *
            FROM lead_contacts
            WHERE company_key = ? AND contact_email = ?
            """,
            (key, email),
        ).fetchone()

        if row:
            return row

    if url:
        row = conn.execute(
            """
            SELECT *
            FROM lead_contacts
            WHERE company_key = ? AND contact_url = ?
            """,
            (key, url),
        ).fetchone()

        if row:
            return row

    return None


def save_contact(conn, key, contact):
    contact = dict(contact)
    contact["contact_email"] = (contact.get("contact_email") or "").lower() or None
    contact["contact_url"] = contact.get("contact_url") or None

    email = contact["contact_email"]
    url = contact["contact_url"]

    existing = find_contact(conn, key, contact)

    now = datetime.now(timezone.utc).isoformat()

    if existing is None:
        conn.execute(
            """
            INSERT OR IGNORE INTO lead_contacts (
                company_key, contact_name, contact_role, contact_email,
                contact_url, contact_type, source_url, confidence,
                verified_at, first_party
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                contact.get("contact_name") or "",
                contact.get("contact_role") or "",
                email,
                url,
                contact.get("contact_type") or "",
                contact.get("source_url") or "",
                contact.get("confidence") or "LOW",
                now,
                1 if contact.get("first_party") else 0,
            ),
        )
        return "NEW"

    if CONTACT_CONFIDENCE_RANK.get(
        contact.get("confidence"), 0
    ) > CONTACT_CONFIDENCE_RANK.get(existing["confidence"], 0):
        conn.execute(
            """
            UPDATE lead_contacts
            SET contact_name = ?, contact_role = ?, contact_email = ?,
                contact_url = ?, contact_type = ?, source_url = ?,
                confidence = ?, verified_at = ?, first_party = ?
            WHERE id = ?
            """,
            (
                contact.get("contact_name") or existing["contact_name"] or "",
                contact.get("contact_role") or existing["contact_role"] or "",
                email or existing["contact_email"],
                url or existing["contact_url"],
                contact.get("contact_type") or existing["contact_type"] or "",
                contact.get("source_url") or existing["source_url"] or "",
                contact.get("confidence"),
                now,
                1 if contact.get("first_party") else existing["first_party"],
                existing["id"],
            ),
        )
        return "UPGRADED"

    return "KNOWN"


def discover_contacts(conn, leads, max_leads=3, fetch_budget=6):
    records = []
    new_count = 0
    upgraded_count = 0
    fetches = 0

    for lead in leads[:max_leads]:
        if fetches >= fetch_budget:
            break

        company = lead["company"]
        key = company_key(company)

        try:
            found, used = discover_contacts_for_lead(
                company,
                lead,
                fetch_budget - fetches,
            )
        except Exception as exc:
            print(
                "CONTACT DISCOVERY FAILED: "
                + safe_error(str(exc)),
                flush=True,
            )
            found, used = [], 0

        fetches += used

        role = choose_target_role(
            lead,
            " ".join(c.get("page_text", "") for c in found),
        )

        candidates = []
        seen_keys = set()

        for contact in found:
            contact.pop("page_text", None)

            if not contact.get("contact_role"):
                contact["contact_role"] = role

            email = (contact.get("contact_email") or "").lower()

            if email:
                local = email.split("@")[0]

                if is_ignored_mailbox(local):
                    continue

                contact["contact_email"] = email

            if contact_rank(contact) <= 0:
                continue

            dedupe_key = email or (contact.get("contact_url") or "").lower()

            if not dedupe_key or dedupe_key in seen_keys:
                continue

            seen_keys.add(dedupe_key)
            candidates.append(contact)

        candidates.sort(
            key=lambda c: (
                contact_rank(c),
                CONTACT_CONFIDENCE_RANK.get(c.get("confidence"), 0),
            ),
            reverse=True,
        )

        best = candidates[0] if candidates else None
        new_for_company = 0

        for contact in candidates:
            already = find_contact(conn, key, contact) is not None

            if not already and new_for_company >= MAX_NEW_CONTACTS_PER_COMPANY:
                continue

            outcome = save_contact(conn, key, contact)

            if outcome == "NEW":
                new_for_company += 1
                new_count += 1
            elif outcome == "UPGRADED":
                upgraded_count += 1

        if best is None:
            best = {
                "contact_name": "",
                "contact_role": role,
                "contact_email": None,
                "contact_url": "",
                "contact_type": "none",
                "source_url": lead.get("source_url", ""),
                "confidence": "LOW",
                "first_party": 0,
            }

        records.append(
            {
                "company": company,
                "contact_name": best.get("contact_name") or "NOT IDENTIFIED",
                "contact_role": best.get("contact_role") or role,
                "contact_email": (
                    best.get("contact_email") or "NOT PUBLICLY VERIFIED"
                ),
                "contact_url": best.get("contact_url") or "",
                "contact_type": best.get("contact_type") or "none",
                "source_url": best.get("source_url") or lead.get("source_url", ""),
                "confidence": best.get("confidence") or "LOW",
            }
        )

    conn.commit()

    return records, new_count, upgraded_count, fetches


def record_research_result(
    conn,
    run_id,
    run_time,
    mission,
    item,
    decision,
    reason,
    key=None,
):
    conn.execute(
        """
        INSERT INTO research_results (
            run_id, run_timestamp, mission, query, result_index,
            title, url, domain, snippet, decision, decision_reason,
            company_key, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            run_time,
            mission,
            str(item.get("query", ""))[:200],
            item.get("id"),
            str(item.get("title", ""))[:300],
            str(item.get("url", ""))[:500],
            domain_from_url(item.get("url", "")),
            str(item.get("snippet", ""))[:700],
            decision,
            str(reason or "")[:200],
            key,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def record_legacy_rejections(conn, run_id, run_time, mission_name, legacy_rejected):
    for item in legacy_rejected or []:
        try:
            record_research_result(
                conn,
                run_id,
                run_time,
                mission_name,
                {
                    "id": None,
                    "query": "legacy-revalidation",
                    "title": item.get("company", ""),
                    "url": item.get("source_url", ""),
                    "snippet": item.get("reason", ""),
                },
                "LEGACY_REJECTED",
                item.get("reason", ""),
                company_key(item.get("company", "")),
            )
        except Exception:
            pass

    try:
        conn.commit()
    except Exception:
        pass


def normalize_query(query):
    text = re.sub(r"[\"'`]", "", str(query or "").lower())
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def recent_normalized_queries(conn, limit=60):
    rows = conn.execute(
        """
        SELECT normalized_query
        FROM search_history
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()

    return {row["normalized_query"] for row in rows}


def record_search_history(conn, run_id, mission, queries, counts_by_query):
    now = datetime.now(timezone.utc).isoformat()

    for query in queries:
        conn.execute(
            """
            INSERT INTO search_history (
                run_id, timestamp, mission, query, normalized_query, results_count
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                now,
                mission,
                query,
                normalize_query(query),
                int(counts_by_query.get(query, 0)),
            ),
        )

    conn.commit()


GEO_ROTATION = (
    "Italy", "Germany", "France", "Spain", "Netherlands", "United Kingdom",
    "Saudi Arabia", "United Arab Emirates", "Nordics", "Benelux", "Poland",
    "Ireland", "Switzerland", "Singapore", "Australia", "Canada",
)


EXPERIMENT_ANGLES = (
    '"ISO 20022" payment exception handling',
    '"ISO 20022" payment repair workflow',
    '"ISO 20022" structured payment data',
    "payment operations automation bank",
    "cross-border payment transformation",
    "transaction banking modernization",
    "payment message validation enterprise",
    "legacy payment transformation",
    "payment orchestration platform",
    "embedded payments ISO 20022",
    "banking-as-a-service payments",
    "treasury payment platform modernization",
)


MISSION_ANGLES = {
    "Banks / ISO 20022": [
        "ISO 20022 migration bank",
        "bank payment modernization",
        "cross-border payment transformation bank",
        "transaction banking modernization",
        "payment repair operations bank",
        "structured payment data bank",
        "payment exception handling bank",
        "legacy payment transformation bank",
    ],
    "PSP / Payment Processors": [
        "payment processor ISO 20022",
        "cross-border PSP modernization",
        "payment operations automation PSP",
        "payment message validation processor",
        "transaction repair workflows PSP",
    ],
    "Fintech": [
        "B2B payments platform",
        "treasury platform ISO 20022",
        "cross-border fintech payments",
        "payment orchestration platform",
        "embedded payments fintech",
        "banking-as-a-service payments",
    ],
    "Europe Research": [
        "ISO 20022 Italy bank",
        "ISO 20022 Germany bank",
        "ISO 20022 France bank",
        "ISO 20022 Spain bank",
        "ISO 20022 Netherlands bank",
        "ISO 20022 United Kingdom bank",
    ],
    "Middle East Research": [
        "ISO 20022 Saudi Arabia bank",
        "ISO 20022 UAE bank",
        "payment modernization Saudi Arabia",
        "payment modernization UAE",
    ],
}


def experiment_queries(mission, offset):
    geos = mission.get("geographies") or list(GEO_ROTATION)
    base = list(EXPERIMENT_ANGLES)
    out = []

    for i in range(min(4, len(base))):
        angle = base[(offset + i) % len(base)]
        geo = geos[(offset + i) % len(geos)] if geos else ""
        out.append(f"{angle} {geo}".strip())

    return out


def plan_queries(conn, mission):
    mission_name = mission.get("name", "")
    pool = list(mission.get("queries", []))
    pool.extend(MISSION_ANGLES.get(mission_name, []))

    recent = recent_normalized_queries(conn)

    runs = conn.execute(
        """
        SELECT COUNT(*)
        FROM research_runs
        WHERE mission = ?
        """,
        (mission_name,),
    ).fetchone()[0]

    if pool:
        offset = int(runs) % len(pool)
        ordered = pool[offset:] + pool[:offset]
    else:
        ordered = []

    chosen = []
    kinds = {}

    for query in ordered:
        normalized = normalize_query(query)

        if not normalized or normalized in recent:
            continue

        chosen.append(query)
        kinds[query] = "exploration"

        if len(chosen) >= 6:
            break

    lead_limit = int(mission.get("existing_lead_limit", 0) or 0)

    if lead_limit:
        for query in existing_lead_queries(conn, lead_limit):
            if len(chosen) >= 8:
                break

            chosen.append(query)
            kinds[query] = "follow_up"

    if len(chosen) < 6:
        for query in experiment_queries(mission, runs):
            normalized = normalize_query(query)

            if normalized in recent or query in chosen:
                continue

            chosen.append(query)
            kinds[query] = "experiment"

            if len(chosen) >= 6:
                break

    return chosen[:8], kinds


def classify_company(conn, company, source_url):
    key = company_key(company)

    if not key:
        return "REJECTED"

    existing = conn.execute(
        """
        SELECT company_key
        FROM leads
        WHERE company_key = ?
        """,
        (key,),
    ).fetchone()

    if existing is None:
        return "NEW_COMPANY"

    if evidence_is_new(conn, key, source_url):
        return "EXISTING_COMPANY_NEW_EVIDENCE"

    return "ALREADY_KNOWN_NO_CHANGE"


def run_workforce(
    mission,
    run_time,
    rejection_stats,
    rejection_examples,
    status,
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
        f"RUN TIME: {run_time} Europe/Rome",
        flush=True,
    )

    print(
        f"MISSION: {mission['name']}",
        flush=True,
    )

    print(
        "=" * 72,
        flush=True,
    )

    conn = init_db()

    status.set_agent(
        "nova",
        "WORKING",
        task="Defining the research mission and target hypothesis",
    )
    status.log("NOVA", "Strategy started")
    status.write()

    print(
        "\n[1/5] CEO / STRATEGY AGENT",
        flush=True,
    )

    strategy = ollama(
        f"""
You are CloudNova's CEO Strategy Agent.

{PRODUCT}

TODAY'S RESEARCH MISSION:
- Name: {mission['name']}
- Target categories: {", ".join(mission.get("categories", [])) or "commercial payment organizations"}
- Geographies: {", ".join(mission.get("geographies", [])) or "worldwide"}

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

Keep the answer below 250 words.

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
        "\n[2/5] REAL WEB RESEARCH AGENT",
        flush=True,
    )

    queries, query_kinds = plan_queries(
        conn,
        mission,
    )

    new_angles = [
        query
        for query, kind in query_kinds.items()
        if kind in ("exploration", "experiment")
    ]

    status.set_agent("nova", "COMPLETE", task="Research strategy prepared")
    status.log("NOVA", "Strategy completed")
    status.set_agent(
        "scout",
        "WORKING",
        task="Searching commercial payment organizations",
    )
    status.log("SCOUT", "Started web research")
    status.set_metric("searchesPlanned", len(queries))
    status.write()

    def _search_progress(done, total, results):
        status.set_agent(
            "scout",
            "WORKING",
            progress=f"{done} / {total} searches",
        )
        status.set_metric("searches", done)
        status.set_metric("resultsInspected", results)
        status.write()

    search_results, search_count = real_web_search(
        queries,
        on_progress=_search_progress,
    )

    print(
        (
            "\nCollected "
            f"{len(search_results)} "
            "real web results from "
            f"{search_count} searches."
        ),
        flush=True,
    )

    counts_by_query = {}

    for item in search_results:
        query = item.get("query", "")
        counts_by_query[query] = counts_by_query.get(query, 0) + 1

    try:
        record_search_history(
            conn,
            status.run_id,
            mission["name"],
            queries,
            counts_by_query,
        )
    except Exception as exc:
        print(
            "SEARCH HISTORY WRITE FAILED: "
            + safe_error(str(exc)),
            flush=True,
        )

    status.set_agent(
        "scout",
        "COMPLETE",
        task=f"{len(search_results)} results inspected",
    )
    status.set_metric("searches", search_count)
    status.set_metric("resultsInspected", len(search_results))
    status.log("SCOUT", "Research candidates collected")
    status.set_agent(
        "verify",
        "WORKING",
        task="Verifying organizations and evidence",
    )
    status.write()

    verified = extract_verified_leads(
        conn,
        status.run_id,
        run_time,
        search_results,
        mission,
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

    status.set_agent(
        "verify",
        "WORKING",
        progress=f"{len(verified)} candidates",
    )
    status.set_metric("candidatesEvaluated", len(verified))
    status.set_metric(
        "rejectedCandidates",
        sum(rejection_stats.values()),
    )
    status.write()

    unique_leads = deduplicate_leads(
        verified
    )

    new_leads, enriched_leads, legacy_rejected = save_or_enrich_leads(
        conn,
        unique_leads,
    )

    print(
        (
            "NEW leads this run: "
            f"{len(new_leads)} | "
            "ENRICHED existing leads: "
            f"{len(enriched_leads)}"
        ),
        flush=True,
    )

    status.set_metric("newLeads", len(new_leads))
    status.set_metric("newCompanies", len(new_leads))
    status.set_metric("enrichedLeads", len(enriched_leads))
    status.set_metric(
        "rejectedCandidates",
        sum(rejection_stats.values()),
    )
    status.set_agent(
        "verify",
        "COMPLETE",
        task=f"{len(new_leads)} new | {len(enriched_leads)} enriched",
    )
    status.log("VERIFY", "Qualification complete")
    status.set_agent(
        "atlas",
        "WORKING",
        task="Enriching existing prospects with stronger evidence",
    )
    status.log("ATLAS", "Enrichment started")
    status.write()

    if legacy_rejected:
        record_legacy_rejections(
            conn,
            status.run_id,
            run_time,
            mission["name"],
            legacy_rejected,
        )
        status.log(
            "VERIFY",
            f"Legacy leads skipped: {len(legacy_rejected)}",
        )
        status.write()

    active_leads = [
        lead
        for lead in (new_leads + enriched_leads)
        if revalidate_lead(lead["company"], lead["source_url"])[0]
    ]

    contact_records, new_contacts_count, upgraded_contacts, contact_fetches = discover_contacts(
        conn,
        active_leads,
        max_leads=3,
        fetch_budget=6,
    )

    print(
        (
            "CONTACTS: "
            f"{len(contact_records)} leads with contact data "
            f"({new_contacts_count} new, {upgraded_contacts} upgraded, "
            f"{contact_fetches} pages fetched)"
        ),
        flush=True,
    )

    status.log(
        "ATLAS",
        f"Contacts discovered: {new_contacts_count} new",
    )
    status.set_metric("newContacts", new_contacts_count)
    status.write()

    contact_by_company = {
        record["company"]: record for record in contact_records
    }

    for lead in active_leads:
        record = contact_by_company.get(lead["company"])
        if record:
            lead["contact"] = record

    for lead in new_leads:
        print_lead_for_review(
            lead
        )

    print(
        "\n[3/5] OUTREACH DRAFT AGENT",
        flush=True,
    )

    status.set_agent(
        "atlas",
        "COMPLETE",
        task=f"{len(enriched_leads)} existing leads enriched",
    )
    status.set_agent(
        "piper",
        "WORKING",
        task="Drafting human-review-required outreach (DRAFT ONLY - not sent)",
    )
    status.log("PIPER", "Drafting outreach (DRAFT ONLY - not sent)")
    status.write()

    outreach_targets = active_leads

    outreach_drafts = create_outreach(
        outreach_targets
    )

    for item in outreach_drafts:
        print(
            (
                f"\n--- DRAFT: {item['company']} ---\n"
                + str(item["draft"])
            ),
            flush=True,
        )

    status.set_agent(
        "piper",
        "COMPLETE",
        task=f"{len(outreach_drafts)} drafts ready - DRAFT ONLY, not sent",
    )
    status.log("PIPER", "Outreach drafts ready - DRAFT ONLY, not sent")
    status.set_agent(
        "sentinel",
        "WORKING",
        task="Challenging qualification and safety guardrails",
    )
    status.log("SENTINEL", "Operations review started")
    status.write()

    print(
        "\n[4/5] OPERATIONS / REVIEW AGENT",
        flush=True,
    )

    outreach_text = "\n\n".join(
        str(item["draft"])
        for item in outreach_drafts
    )

    review = operations_review(
        outreach_targets,
        outreach_text,
    )

    print(
        review,
        flush=True,
    )

    status.set_agent(
        "sentinel",
        "COMPLETE",
        task="Run reviewed - human approval required",
    )
    status.log("SENTINEL", "Operations review complete")
    status.write()

    print(
        "\n[5/5] PERSIST + SUMMARY",
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

    rejected_count = sum(
        rejection_stats.values()
    )

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

    status.set_metric("reviewRequired", review_count)
    status.log(
        "NOVA",
        "Run complete - operator report follows; no prospect emails sent",
    )
    status.complete()

    conn.close()

    return {
        "mission_name": mission["name"],
        "run_time": run_time,
        "search_count": search_count,
        "results_count": len(search_results),
        "qualified_count": len(verified),
        "new_leads": new_leads,
        "enriched_leads": enriched_leads,
        "rejected_count": rejected_count,
        "outreach_drafts": outreach_drafts,
        "review": review,
        "total": total,
        "review_count": review_count,
        "contacts": contact_records,
        "new_companies": [lead["company"] for lead in new_leads],
        "new_contacts_count": new_contacts_count,
        "new_angles": new_angles,
        "legacy_rejected": legacy_rejected,
    }


def record_research_run(
    conn,
    run_time,
    mission_name,
    search_count,
    results_count,
    qualified_count,
    new_leads_count,
    enriched_count,
    rejected_count,
    run_status,
):
    conn.execute(
        """
        INSERT INTO research_runs (
            run_timestamp,
            mission,
            search_count,
            results_count,
            qualified_count,
            new_leads_count,
            enriched_count,
            rejected_count,
            run_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_time,
            mission_name,
            int(search_count),
            int(results_count),
            int(qualified_count),
            int(new_leads_count),
            int(enriched_count),
            int(rejected_count),
            run_status,
        ),
    )

    conn.commit()


def main():
    rejection_stats = new_rejection_stats()
    rejection_examples = new_rejection_examples()

    mission = get_research_mission()
    run_time = rome_timestamp()

    status = WorkforceStatus(mission["name"], run_time)
    status.log("NOVA", "Workforce run started")
    status.write()

    run_status = "NO_NEW_LEADS"

    data = {
        "mission_name": mission["name"],
        "run_time": run_time,
        "search_count": 0,
        "results_count": 0,
        "qualified_count": 0,
        "new_leads": [],
        "enriched_leads": [],
        "rejected_count": 0,
        "outreach_drafts": [],
        "review": "",
        "total": 0,
        "review_count": 0,
        "contacts": [],
        "new_companies": [],
        "new_contacts_count": 0,
        "new_angles": [],
        "legacy_rejected": [],
    }

    try:
        data = run_workforce(
            mission,
            run_time,
            rejection_stats,
            rejection_examples,
            status,
        )

        if data["new_leads"]:
            run_status = "NEW_LEADS_REVIEW_REQUIRED"
        elif data["enriched_leads"]:
            run_status = "LEADS_ENRICHED_REVIEW_REQUIRED"
        else:
            run_status = "NO_NEW_LEADS"

    except Exception as exc:
        run_status = "ERROR"
        status.fail()
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

    try:
        conn = init_db()

        record_research_run(
            conn,
            run_time,
            data["mission_name"],
            data["search_count"],
            data["results_count"],
            data["qualified_count"],
            len(data["new_leads"]),
            len(data["enriched_leads"]),
            data["rejected_count"],
            run_status,
        )

        conn.close()

    except Exception as exc:
        print(
            "RESEARCH RUN PERSIST FAILED: "
            + safe_error(str(exc)),
            flush=True,
        )

    report_subject = (
        "CloudNova Workforce Report - "
        f"{data['mission_name']} - "
        f"{run_time} Europe/Rome"
    )

    report_body = build_daily_report(
        run_time,
        data["mission_name"],
        run_status,
        data["search_count"],
        data["results_count"],
        data["qualified_count"],
        data["new_leads"],
        data["enriched_leads"],
        rejection_stats,
        rejection_examples,
        data["outreach_drafts"],
        data["review"],
        data["total"],
        data["review_count"],
        data.get("contacts", []),
        data.get("new_companies", []),
        data.get("new_contacts_count", 0),
        data.get("new_angles", []),
        data.get("legacy_rejected", []),
    )

    send_daily_report(
        report_subject,
        report_body,
    )


if __name__ == "__main__":
    main()
