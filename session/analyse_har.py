#!/usr/bin/env python3
"""
analyse_har.py — Analyse a browser HAR file for OIDC session lifecycle events.

Use this to examine a HAR recording from a browser session that experienced
unexpected logouts. It extracts:
  - First and last successful API call (session start / loss boundary)
  - All requests that returned 401 with the SignedOut envelope
  - Burst patterns: groups of >=3 requests within 250ms (the race-trigger condition)
  - OIDC redirect chain (/api/v2/users/oidc/callback)
  - Cookie lifecycle: when coder_session_token is set, cleared, replaced

Usage:
  python analyse_har.py <file.har>
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SIGNED_OUT_MARKER = 'Cookie "coder_session_token" or query parameter must be provided'


def parse_ts(s):
    """Parse HAR ISO 8601 timestamp."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    if len(sys.argv) != 2:
        print("Usage: analyse_har.py <file.har>", file=sys.stderr)
        return 2

    har_path = Path(sys.argv[1])
    if not har_path.exists():
        print(f"File not found: {har_path}", file=sys.stderr)
        return 1

    har = json.loads(har_path.read_text())
    entries = har["log"]["entries"]

    print(f"Total HTTP entries: {len(entries)}")
    if not entries:
        return 0

    start = parse_ts(entries[0]["startedDateTime"])
    end = parse_ts(entries[-1]["startedDateTime"])
    print(f"Span: {start.isoformat()} -> {end.isoformat()} ({(end - start).total_seconds():.0f}s)")

    # 1. Find every 401 with the signed-out message
    print("\n--- 401 SignedOut events ---")
    signed_out = []
    for e in entries:
        if e["response"]["status"] == 401:
            body = e["response"].get("content", {}).get("text", "")
            if SIGNED_OUT_MARKER in body:
                signed_out.append(e)
                ts = parse_ts(e["startedDateTime"])
                print(f"  {ts.isoformat()}  {e['request']['method']} {e['request']['url'][:100]}")
    print(f"  Total: {len(signed_out)}")

    # 2. Cookie lifecycle
    print("\n--- coder_session_token cookie events ---")
    cookie_events = 0
    for e in entries:
        for c in e["response"].get("cookies", []):
            if c["name"] == "coder_session_token":
                ts = parse_ts(e["startedDateTime"])
                action = "CLEARED" if c.get("value") == "" else f"SET (expires={c.get('expires', '?')})"
                print(f"  {ts.isoformat()}  {action}  via {e['request']['url'][:80]}")
                cookie_events += 1
    if cookie_events == 0:
        print("  (none recorded)")

    # 3. Burst detection — concurrent requests that could trigger the race
    print("\n--- Concurrent request bursts (>=3 within 250ms to /api/v2/) ---")
    api_entries = [
        (parse_ts(e["startedDateTime"]), e["request"]["url"])
        for e in entries
        if "/api/v2/" in e["request"]["url"]
    ]
    api_entries.sort()
    i = 0
    burst_count = 0
    while i < len(api_entries):
        window_end = api_entries[i][0] + timedelta(milliseconds=250)
        j = i
        while j < len(api_entries) and api_entries[j][0] <= window_end:
            j += 1
        if j - i >= 3:
            burst_count += 1
            print(f"  {api_entries[i][0].isoformat()}  {j - i} requests in 250ms:")
            for ts, url in api_entries[i:j]:
                path = url.split("?")[0]
                print(f"    {ts.time()}  {path[:80]}")
            i = j
        else:
            i += 1
    print(f"  Total bursts: {burst_count}")

    # 4. OIDC redirect chain
    print("\n--- OIDC callback / login events ---")
    oidc_events = 0
    for e in entries:
        url = e["request"]["url"]
        if "oidc/callback" in url or "/login" in url or "sso." in url.lower():
            ts = parse_ts(e["startedDateTime"])
            print(f"  {ts.isoformat()}  {e['response']['status']}  {e['request']['method']}  {url[:100]}")
            oidc_events += 1
    if oidc_events == 0:
        print("  (none recorded)")

    # 5. Distribution of response codes
    print("\n--- Status code distribution (api/v2 only) ---")
    counts = defaultdict(int)
    for e in entries:
        if "/api/v2/" in e["request"]["url"]:
            counts[e["response"]["status"]] += 1
    for code, n in sorted(counts.items()):
        print(f"  {code}: {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
