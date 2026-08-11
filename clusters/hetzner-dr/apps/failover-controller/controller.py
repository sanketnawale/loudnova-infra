import json
import os
import time
import urllib.request
import urllib.error
import smtplib
from email.message import EmailMessage


TOKEN = os.environ["CF_API_TOKEN"]
ZONE_ID = os.environ["CF_ZONE_ID"]
RECORD_ID = os.environ["CF_RECORD_ID"]

PRIMARY_TUNNEL = os.environ["PRIMARY_TUNNEL"]
DR_TUNNEL = os.environ["DR_TUNNEL"]

PRIMARY_HEALTH = os.environ["PRIMARY_HEALTH_URL"]
DR_HEALTH = os.environ["DR_HEALTH_URL"]

INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
FAIL_THRESHOLD = int(os.getenv("FAIL_THRESHOLD", "3"))
RECOVER_THRESHOLD = int(os.getenv("RECOVER_THRESHOLD", "5"))

SMTP_HOST = os.environ["SMTP_HOST"]
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ["SMTP_USERNAME"]
SMTP_PASSWORD = os.environ["SMTP_PASSWORD"]
SMTP_FROM = os.environ["SMTP_FROM"]
SMTP_TO = os.environ["SMTP_TO"]

API = (
    f"https://api.cloudflare.com/client/v4/zones/"
    f"{ZONE_ID}/dns_records/{RECORD_ID}"
)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}


def send_mail(subject, message):
    try:
        mail = EmailMessage()
        mail["Subject"] = subject
        mail["From"] = SMTP_FROM
        mail["To"] = SMTP_TO
        mail.set_content(message)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(mail)

        print(f"EMAIL SENT: {subject}", flush=True)

    except Exception as e:
        print(f"EMAIL ERROR: {e}", flush=True)


def health(url):
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "cloudnova-dr-controller/1.0"},
        )

        with urllib.request.urlopen(req, timeout=10) as r:
            body = (
                r.read()
                .decode("utf-8", errors="ignore")
                .strip()
                .lower()
            )

            return (
                200 <= r.status < 300
                and "healthy" in body
            )

    except Exception as e:
        print(f"HEALTH ERROR {url}: {e}", flush=True)
        return False


def current_target():
    req = urllib.request.Request(API, headers=HEADERS)

    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())

    return data["result"]["content"]


def switch(target):
    body = json.dumps(
        {
            "type": "CNAME",
            "name": "cloudnova.tech",
            "content": target,
            "proxied": True,
            "ttl": 1,
        }
    ).encode()

    req = urllib.request.Request(
        API,
        data=body,
        headers=HEADERS,
        method="PATCH",
    )

    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())

    if not data.get("success"):
        raise RuntimeError(data)

    print(
        f"SWITCHED cloudnova.tech -> {target}",
        flush=True,
    )


primary_failures = 0
primary_successes = 0

both_unhealthy_notified = False

print("CloudNova DR controller started", flush=True)


while True:
    primary_ok = health(PRIMARY_HEALTH)
    dr_ok = health(DR_HEALTH)

    if primary_ok:
        primary_failures = 0
        primary_successes += 1
    else:
        primary_successes = 0
        primary_failures += 1

    try:
        target = current_target()

        print(
            f"primary={primary_ok} dr={dr_ok} "
            f"failures={primary_failures}/{FAIL_THRESHOLD} "
            f"successes={primary_successes}/{RECOVER_THRESHOLD} "
            f"target={target}",
            flush=True,
        )

        # PRIMARY failure -> DR
        if (
            primary_failures >= FAIL_THRESHOLD
            and dr_ok
            and target != DR_TUNNEL
        ):
            print(
                "FAILOVER: primary unhealthy, activating DR",
                flush=True,
            )

            switch(DR_TUNNEL)

            send_mail(
                "CloudNova DR - FAILOVER",
                (
                    "Automatic DR failover completed.\n\n"
                    "Primary environment became unhealthy.\n"
                    "Traffic has been switched to the DR environment.\n\n"
                    "Status: DR ACTIVE"
                ),
            )

            both_unhealthy_notified = False

        # PRIMARY recovered -> preferred PRIMARY
        elif (
            primary_successes >= RECOVER_THRESHOLD
            and target == DR_TUNNEL
        ):
            print(
                "FAILBACK: primary stable, restoring LoudNova",
                flush=True,
            )

            switch(PRIMARY_TUNNEL)

            send_mail(
                "CloudNova DR - FAILBACK",
                (
                    "Automatic DR failback completed.\n\n"
                    "The primary environment has recovered "
                    "and remained healthy.\n"
                    "Traffic has been restored to the "
                    "preferred primary environment.\n\n"
                    "Status: PRIMARY ACTIVE"
                ),
            )

            both_unhealthy_notified = False

        elif (
            primary_failures >= FAIL_THRESHOLD
            and not dr_ok
        ):
            print(
                "CRITICAL: primary unhealthy AND DR unhealthy "
                "- no DNS change",
                flush=True,
            )

            if not both_unhealthy_notified:
                send_mail(
                    "CloudNova DR - CRITICAL",
                    (
                        "Both the primary and DR environments "
                        "are unhealthy.\n\n"
                        "No DNS change has been performed.\n"
                        "Manual investigation is required."
                    ),
                )

                both_unhealthy_notified = True

        else:
            if primary_ok or dr_ok:
                both_unhealthy_notified = False

    except Exception as e:
        print(f"CONTROLLER ERROR: {e}", flush=True)

        send_mail(
            "CloudNova DR - Controller Error",
            (
                "The DR controller encountered an error.\n\n"
                f"Error: {e}"
            ),
        )

    time.sleep(INTERVAL)