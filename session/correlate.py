#!/usr/bin/env python3
"""
correlate.py - Cross-reference session_monitor.py JSONL output with the 401
SignedOut events extracted from a browser HAR capture.

Useful when you have both:
  1. A JSONL file from session_monitor.py running against a deployment
  2. A HAR captured in DevTools spanning the same window

...and you want to confirm the script and the browser observed the same
session-loss event (within a configurable time delta).

Usage:
  python correlate.py --jsonl session_monitor.jsonl --har capture.har
  python correlate.py --jsonl my.jsonl --har my.har --window-seconds 30
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SIGNED_OUT_MARKER = 'Cookie "coder_session_token" or query parameter must be provided'


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_jsonl(path):
    """Read session_monitor.py JSONL output."""
    out = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


def load_har_signed_out(path):
    """Extract timestamps of 401 SignedOut responses from a HAR file."""
    har = json.loads(Path(path).read_text())
    out = []
    for e in har["log"]["entries"]:
        if e["response"]["status"] != 401:
            continue
        body = e["response"].get("content", {}).get("text", "") or ""
        # HAR bodies may be JSON-escaped (\"coder_session_token\") or raw
        # ("coder_session_token"). Check both forms.
        if SIGNED_OUT_MARKER in body or SIGNED_OUT_MARKER.replace(chr(34), chr(92) + chr(34)) in body:
            out.append({
                "ts": parse_ts(e["startedDateTime"]),
                "url": e["request"]["url"],
            })
    return out


def nearest(target, candidates, max_delta_seconds):
    """Find the candidate with smallest |ts - target| within max_delta."""
    best = None
    for c in candidates:
        d = abs((c["ts"] - target).total_seconds())
        if d <= max_delta_seconds and (best is None or d < best[1]):
            best = (c, d)
    return best


def format_row(target_ts, match, window_seconds):
    if match is None:
        return f"  {target_ts.isoformat()}  -> (no HAR 401 within {window_seconds}s)"
    cand, delta = match
    return f"  {target_ts.isoformat()}  -> {cand['ts'].isoformat()}  (delta={delta:.1f}s)"


def main():
    parser = argparse.ArgumentParser(
        description="Correlate session_monitor.py JSONL with HAR 401 events.",
    )
    parser.add_argument("--jsonl", required=True, help="session_monitor.jsonl path")
    parser.add_argument("--har", required=True, help="HAR file path")
    parser.add_argument("--window-seconds", type=int, default=60,
                        help="Max time delta for correlation (default: 60)")
    args = parser.parse_args()

    bursts = load_jsonl(args.jsonl)
    har_events = load_har_signed_out(args.har)

    lost = [parse_ts(b["ts"]) for b in bursts if b["label"] == "SESSION_LOST"]
    refresh = [parse_ts(b["ts"]) for b in bursts if b["label"].startswith("REFRESH_LIKELY")]

    print(f"JSONL bursts:           {len(bursts)}")
    print(f"  SESSION_LOST:         {len(lost)}")
    print(f"  REFRESH_LIKELY:       {len(refresh)}")
    print(f"HAR SignedOut 401s:     {len(har_events)}")
    print(f"Correlation window:     +/- {args.window_seconds}s")
    print()

    if lost:
        print("--- SESSION_LOST bursts -> nearest HAR 401 ---")
        matched = 0
        for t in lost:
            m = nearest(t, har_events, args.window_seconds)
            print(format_row(t, m, args.window_seconds))
            if m is not None:
                matched += 1
        print(f"  matched: {matched}/{len(lost)}")
        print()

    print("--- Verdict ---")
    if not lost and not har_events:
        print("  No session loss observed in either source during the capture window.")
    elif lost and not har_events:
        print("  Script observed session loss but HAR has no SignedOut 401s.")
        print("  Likely cause: HAR window does not cover the failure, or browser was idle.")
    elif har_events and not lost:
        print("  HAR shows SignedOut 401s but script did not.")
        print("  Run session_monitor.py longer or with a smaller --interval to catch it.")
    else:
        matched = sum(1 for t in lost if nearest(t, har_events, args.window_seconds) is not None)
        if matched == len(lost):
            print("  All script SESSION_LOST events correlate with HAR 401s.")
            print("  Strong evidence the script and browser observed the same event.")
        else:
            print(f"  {matched}/{len(lost)} script SESSION_LOST events correlate with HAR 401s.")
            print("  Unmatched events may indicate the HAR did not span them.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
