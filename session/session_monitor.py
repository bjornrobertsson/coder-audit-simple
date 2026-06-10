#!/usr/bin/env python3
"""
session_monitor.py — Probe a Coder session and log the lifecycle of an OIDC refresh.

Fires parallel API requests to emulate the browser's burst pattern that can trigger
OIDC token refresh race conditions. Logs every response to JSONL for later analysis.

Environment:
  CODER_URL             Base URL of your Coder deployment
  CODER_SESSION_TOKEN   Browser session token (from coder_session_token cookie)
  - or -
  CODER_TOKEN           API token (works but won't trigger OIDC refresh path)

Usage:
  python session_monitor.py --interval 5 --duration 3600 --concurrent 5
  python session_monitor.py --interval 3 --duration 600 --concurrent 8 --output my_session.jsonl
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Helpers (matching coder-audit-simple conventions)
# ---------------------------------------------------------------------------

def get_token():
    """Read session/API token from env or audit-token.txt."""
    token = os.environ.get("CODER_SESSION_TOKEN") or os.environ.get("CODER_TOKEN")
    if token:
        return token
    token_file = Path(__file__).parent.parent / "audit-token.txt"
    if token_file.exists():
        return token_file.read_text().strip()
    return None


def get_fqdn():
    """Read Coder URL from env."""
    return os.environ.get("CODER_URL", "").rstrip("/")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

def probe(session, base_url, path):
    """Single GET request with timing."""
    url = f"{base_url}{path}"
    t0 = time.monotonic()
    started = now_iso()
    try:
        resp = session.get(url, timeout=30)
        elapsed_ms = (time.monotonic() - t0) * 1000
        body_snippet = resp.text[:300] if resp.status_code >= 400 else ""
        return {
            "ts": started,
            "path": path,
            "status": resp.status_code,
            "latency_ms": round(elapsed_ms, 1),
            "body": body_snippet,
            "request_id": resp.headers.get("x-request-id", ""),
        }
    except Exception as e:
        return {
            "ts": started,
            "path": path,
            "status": -1,
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "error": str(e),
        }


def burst(session, base_url, n):
    """Fire N parallel requests to /api/v2/users/me — the race-triggering pattern."""
    results = []
    with ThreadPoolExecutor(max_workers=n) as executor:
        futures = [executor.submit(probe, session, base_url, "/api/v2/users/me") for _ in range(n)]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def classify(results):
    """Classify a burst of results."""
    statuses = [r["status"] for r in results]
    if all(s == 200 for s in statuses):
        max_lat = max(r["latency_ms"] for r in results)
        if max_lat > 2000:
            return f"REFRESH_LIKELY (max_latency={max_lat:.0f}ms)"
        return "OK"
    if any(s == 401 for s in statuses):
        return "SESSION_LOST"
    if any(s >= 500 for s in statuses):
        return "SERVER_ERROR"
    if any(s == -1 for s in statuses):
        return "NETWORK_ERROR"
    return f"MIXED ({statuses})"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=5.0, help="Seconds between bursts (default: 5)")
    ap.add_argument("--duration", type=int, default=3600, help="Total run time in seconds (default: 3600)")
    ap.add_argument("--concurrent", type=int, default=5, help="Parallel requests per burst (default: 5)")
    ap.add_argument("--output", default="session_monitor.jsonl", help="Output JSONL file")
    args = ap.parse_args()

    base_url = get_fqdn()
    token = get_token()

    if not base_url:
        print("Error: Set CODER_URL environment variable", file=sys.stderr)
        return 2
    if not token:
        print("Error: Set CODER_SESSION_TOKEN or CODER_TOKEN, or create audit-token.txt", file=sys.stderr)
        return 2

    headers = {
        "Coder-Session-Token": token,
        "Accept": "application/json",
    }
    session = requests.Session()
    session.headers.update(headers)

    print(f"Monitoring {base_url}")
    print(f"Interval: {args.interval}s, Duration: {args.duration}s, Concurrent: {args.concurrent}")
    print(f"Output: {args.output}")
    print("-" * 60)

    out = Path(args.output).open("w")
    summary = {}
    deadline = time.monotonic() + args.duration

    i = 0
    while time.monotonic() < deadline:
        results = burst(session, base_url, args.concurrent)
        label = classify(results)
        summary[label] = summary.get(label, 0) + 1
        record = {"ts": now_iso(), "burst": i, "label": label, "results": results}
        out.write(json.dumps(record) + "\n")
        out.flush()

        # Live signal — print only state changes and anomalies
        if label != "OK" or i % 12 == 0:
            print(f"{record['ts']}  burst={i:4d}  {label}")
        if label == "SESSION_LOST":
            print("Session lost — stopping. See output JSONL for the full timeline.")
            break

        i += 1
        time.sleep(args.interval)

    out.close()
    print("\n--- Summary ---")
    for k, v in sorted(summary.items(), key=lambda kv: -kv[1]):
        print(f"  {k:30s}  {v}")
    print(f"\nFull log: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
