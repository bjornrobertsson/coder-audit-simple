# Session Monitoring Tools

Tools for diagnosing OIDC session timeout issues in Coder deployments.

## Background

When Coder is configured with OIDC authentication and the IdP uses short-lived rotating refresh tokens, a race condition can occur during token refresh. Multiple parallel API requests from the browser can each attempt to use the same single-use refresh token, causing session invalidation.

These tools help capture and analyse the timing of these events.

## Tools

### session_monitor.py

Probes a Coder session by firing parallel API requests at regular intervals. This emulates the browser's burst pattern that can trigger the race condition.

```bash
# Set environment
export CODER_URL=https://coder.example.com
export CODER_SESSION_TOKEN=<paste from browser DevTools coder_session_token cookie>

# Run for 1 hour, 5 parallel requests every 5 seconds
python session/session_monitor.py --interval 5 --duration 3600 --concurrent 5

# Shorter test run
python session/session_monitor.py --interval 3 --duration 600 --concurrent 8
```

Output signals:
- `OK` — All requests succeeded normally
- `REFRESH_LIKELY (max_latency=XXXXms)` — High latency suggests IdP refresh occurred
- `SESSION_LOST` — 401 response, session was invalidated
- `SERVER_ERROR` — 5xx response during refresh attempt

### analyse_har.py

Analyses a HAR file recorded from browser DevTools during a session timeout event.

```bash
# Record HAR in browser:
# 1. Open DevTools → Network tab
# 2. Enable "Preserve log"
# 3. Use Coder normally until timeout occurs
# 4. Right-click → "Save all as HAR"

python session/analyse_har.py session_recording.har
```

Extracts:
- 401 SignedOut events with timestamps
- Cookie set/clear lifecycle
- Request bursts (≥3 requests within 250ms) that could trigger race
- OIDC callback events
- Status code distribution

## Interpreting Results

### From session_monitor.py JSONL output

Look for patterns like:
```
{"ts": "...", "burst": 142, "label": "REFRESH_LIKELY (max_latency=3200ms)", ...}
{"ts": "...", "burst": 143, "label": "SESSION_LOST", ...}
```

The burst before `SESSION_LOST` with high latency indicates the refresh was attempted but failed.

### From HAR analysis

Look for:
1. Burst of ≥3 requests within 250ms
2. Followed immediately by 401 responses
3. OIDC callback showing re-authentication

## Cross-referencing with IdP Audit Logs

The timestamps from these tools can be used to request specific IdP audit logs. Ask the IdP team for logs within ±2 minutes of any `SESSION_LOST` event, looking for:
1. A successful `refresh_token` grant
2. Followed within milliseconds by `invalid_grant` errors for the same token

## Requirements

```bash
pip install requests tabulate
```

## Related Issues

- Race condition in OIDC refresh: Coder PR #25301 (closed/stale)
- Singleflight pattern for external auth: Coder PR #22904 (merged, external auth only)
