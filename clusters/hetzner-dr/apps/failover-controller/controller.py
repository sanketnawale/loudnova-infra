import json
import os
import time
import urllib.request
import urllib.error

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

API = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{RECORD_ID}"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}


def health(url):
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "cloudnova-dr-controller/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode("utf-8", errors="ignore").strip().lower()
            return 200 <= r.status < 300 and "healthy" in body
    except Exception as e:
        print(f"HEALTH ERROR {url}: {e}", flush=True)
        return False


def current_target():
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
        return data["result"]["content"]


def switch(target):
    body = json.dumps({
        "type": "CNAME",
        "name": "cloudnova.tech",
        "content": target,
        "proxied": True,
        "ttl": 1,
    }).encode()

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

    print(f"SWITCHED cloudnova.tech -> {target}", flush=True)


primary_failures = 0
primary_successes = 0

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
            print("FAILOVER: primary unhealthy, activating DR", flush=True)
            switch(DR_TUNNEL)

        # PRIMARY recovered -> preferred PRIMARY
        elif (
            primary_successes >= RECOVER_THRESHOLD
            and target == DR_TUNNEL
        ):
            print("FAILBACK: primary stable, restoring LoudNova", flush=True)
            switch(PRIMARY_TUNNEL)

        elif primary_failures >= FAIL_THRESHOLD and not dr_ok:
            print(
                "CRITICAL: primary unhealthy AND DR unhealthy - no DNS change",
                flush=True,
            )

    except Exception as e:
        print(f"CONTROLLER ERROR: {e}", flush=True)

    time.sleep(INTERVAL)
