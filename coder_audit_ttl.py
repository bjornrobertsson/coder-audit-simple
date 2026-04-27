#!/usr/bin/env python3
"""Combined workspace audit and TTL update tool for Coder.

This script merges the useful parts of `coder_audit.py` and
`get_and_bump_ttl_workspaces.py` into one CLI:

- `report` shows running workspaces with current TTL and deadline data.
- `set-ttl` updates a workspace TTL by workspace ID.

Authentication matches the existing repository behavior:

1. Read `audit-token.txt` from the current working directory or the script
   directory.
2. Fall back to the `CODER_TOKEN` environment variable.
3. Read the base URL from `CODER_URL`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None


REQUEST_TIMEOUT = 30
ZERO_TIME = "0001-01-01T00:00:00Z"
ALL_RESULTS_LIMIT = 0
TTL_MIN_MS = 60_000
TTL_MAX_MS = 30 * 24 * 60 * 60 * 1000


class CoderError(RuntimeError):
    """Raised when the Coder API request fails."""


@dataclass(frozen=True)
class Config:
    """Runtime configuration for the script."""

    base_url: str
    token: str


class CoderClient:
    """Small wrapper around the Coder API used by this script."""

    def __init__(self, config: Config) -> None:
        self.base_url = config.base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Coder-Session-Token": config.token,
            }
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        expected_statuses: Iterable[int] = (200,),
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        response = self.session.request(
            method,
            url,
            timeout=REQUEST_TIMEOUT,
            json=json_body,
            params=params,
        )
        if response.status_code not in tuple(expected_statuses):
            raise CoderError(
                f"{method} {path} failed with {response.status_code}: "
                f"{response.text.strip()}"
            )
        if not response.content:
            return None
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise CoderError(
                f"{method} {path} returned invalid JSON."
            ) from exc

    def get_audit_logs(self) -> list[dict[str, Any]]:
        payload = self.request(
            "GET", "/api/v2/audit", params={"limit": ALL_RESULTS_LIMIT}
        )
        if isinstance(payload, dict):
            logs = payload.get("audit_logs", [])
            return logs if isinstance(logs, list) else []
        return []

    def get_workspace(self, workspace_id: str) -> dict[str, Any]:
        payload = self.request("GET", f"/api/v2/workspaces/{workspace_id}")
        return payload if isinstance(payload, dict) else {}

    def get_workspaces(self) -> list[dict[str, Any]]:
        payload = self.request(
            "GET", "/api/v2/workspaces", params={"limit": ALL_RESULTS_LIMIT}
        )
        if isinstance(payload, dict):
            workspaces = payload.get("workspaces", [])
            return workspaces if isinstance(workspaces, list) else []
        if isinstance(payload, list):
            return payload
        return []

    def get_templates(self) -> dict[str, str]:
        payload = self.request("GET", "/api/v2/templates")
        if isinstance(payload, dict):
            templates = payload.get("templates", [])
        else:
            templates = payload
        if not isinstance(templates, list):
            return {}
        return {
            str(template.get("id")): str(template.get("name"))
            for template in templates
            if template.get("id") and template.get("name")
        }

    def update_workspace_ttl(
        self, workspace_id: str, ttl_ms: int | None, *, dry_run: bool = False
    ) -> None:
        if dry_run:
            return
        self.request(
            "PUT",
            f"/api/v2/workspaces/{workspace_id}/ttl",
            expected_statuses=(200, 204),
            json_body={"ttl_ms": ttl_ms},
        )


def read_token_file() -> str | None:
    """Read the token file from the working directory or script directory."""

    search_paths = [
        Path.cwd() / "audit-token.txt",
        Path(__file__).resolve().with_name("audit-token.txt"),
    ]
    for path in search_paths:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return None



def load_config() -> Config:
    token = read_token_file() or os.environ.get("CODER_TOKEN", "").strip()
    if not token:
        raise CoderError(
            "Missing token. Set CODER_TOKEN or create audit-token.txt."
        )

    base_url = os.environ.get("CODER_URL", "").strip()
    if not base_url:
        raise CoderError("Missing CODER_URL.")

    return Config(base_url=base_url, token=token)



def parse_iso8601(value: Any) -> datetime | None:
    if not value or value == ZERO_TIME:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None



def format_datetime(value: Any) -> str:
    parsed = parse_iso8601(value)
    if not parsed:
        return "N/A"
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")



def format_ttl(ttl_ms: Any) -> str:
    if ttl_ms is None:
        return "N/A"
    try:
        remaining_seconds = int(ttl_ms) // 1000
    except (TypeError, ValueError):
        return "N/A"

    if remaining_seconds < 60:
        return f"{remaining_seconds}s"

    minutes, seconds = divmod(remaining_seconds, 60)
    if minutes < 60:
        return f"{minutes}m"

    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h"

    days, hours = divmod(hours, 24)
    if hours:
        return f"{days}d {hours}h"
    return f"{days}d"



def format_time_remaining(deadline: Any) -> str:
    parsed = parse_iso8601(deadline)
    if not parsed:
        return "N/A"

    now = datetime.now(timezone.utc)
    if parsed <= now:
        return "Expired"

    total_seconds = int((parsed - now).total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"



def normalize_additional_fields(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}



def latest_start_by_workspace(
    audit_logs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}

    for log in audit_logs:
        if log.get("resource_type") != "workspace_build":
            continue
        if log.get("action") != "start":
            continue

        fields = normalize_additional_fields(log.get("additional_fields"))
        workspace_id = fields.get("workspace_id")
        if not workspace_id:
            continue

        log_time = parse_iso8601(log.get("time"))
        if not log_time:
            continue

        previous = latest.get(str(workspace_id))
        if previous and log_time <= previous["dt"]:
            continue

        user = log.get("user") or {}
        latest[str(workspace_id)] = {
            "dt": log_time,
            "username": user.get("username") or "N/A",
            "workspace_name": fields.get("workspace_name") or log.get("resource_target") or "N/A",
        }

    return latest



def build_report_rows(
    workspaces: list[dict[str, Any]],
    templates: dict[str, str],
    latest_starts: dict[str, dict[str, Any]],
    *,
    include_stopped: bool,
    owner_filter: str | None,
    workspace_filter: str | None,
) -> list[list[str]]:
    rows: list[list[str]] = []

    owner_filter = owner_filter.lower() if owner_filter else None
    workspace_filter = workspace_filter.lower() if workspace_filter else None

    for workspace in workspaces:
        latest_build = workspace.get("latest_build") or {}
        status = str(latest_build.get("status") or "unknown")
        if not include_stopped and status != "running":
            continue

        owner_name = str(workspace.get("owner_name") or "N/A")
        workspace_name = str(workspace.get("name") or "N/A")
        if owner_filter and owner_filter not in owner_name.lower():
            continue
        if workspace_filter and workspace_filter not in workspace_name.lower():
            continue

        workspace_id = str(workspace.get("id") or "")
        latest_start = latest_starts.get(workspace_id, {})

        template_name = (
            workspace.get("template_name")
            or templates.get(str(workspace.get("template_id")), "Unknown")
        )

        owner_info = workspace.get("owner") or {}
        last_seen = owner_info.get("last_seen_at") or workspace.get("last_used_at")

        rows.append(
            [
                owner_name,
                workspace_name,
                str(template_name),
                status,
                format_datetime(latest_start.get("dt")),
                format_datetime(last_seen),
                format_ttl(workspace.get("ttl_ms")),
                format_time_remaining(latest_build.get("deadline")),
                format_datetime(latest_build.get("deadline")),
                format_datetime(latest_build.get("max_deadline")),
                workspace_id or "N/A",
            ]
        )

    rows.sort(key=lambda row: (row[0].lower(), row[1].lower()))
    return rows



def print_table(headers: list[str], rows: list[list[str]]) -> None:
    if tabulate is not None:
        print(tabulate(rows, headers=headers, tablefmt="grid"))
        return

    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(str(value)))

    def fmt_row(values: list[str]) -> str:
        return " | ".join(
            str(value).ljust(widths[index]) for index, value in enumerate(values)
        )

    separator = "-+-".join("-" * width for width in widths)
    print(fmt_row(headers))
    print(separator)
    for row in rows:
        print(fmt_row(row))



def cmd_report(args: argparse.Namespace) -> int:
    client = CoderClient(load_config())
    workspaces = client.get_workspaces()
    templates = client.get_templates()
    audit_logs = client.get_audit_logs()
    latest_starts = latest_start_by_workspace(audit_logs)

    headers = [
        "Username",
        "Workspace",
        "Template",
        "Status",
        "Last Start",
        "Last Seen",
        "TTL",
        "Until Stop",
        "Deadline",
        "Max Deadline",
        "Workspace ID",
    ]
    rows = build_report_rows(
        workspaces,
        templates,
        latest_starts,
        include_stopped=args.include_stopped,
        owner_filter=args.owner,
        workspace_filter=args.workspace,
    )

    if args.json:
        payload = [dict(zip(headers, row)) for row in rows]
        print(json.dumps(payload, indent=2))
        return 0

    if not rows:
        print("No matching workspaces found.")
        return 0

    print_table(headers, rows)
    print(f"\nRows: {len(rows)}")
    return 0



def validate_workspace_id(workspace_id: str) -> str:
    try:
        return str(uuid.UUID(workspace_id))
    except ValueError as exc:
        raise CoderError(f"Invalid workspace UUID: {workspace_id}") from exc



def validate_ttl_ms(ttl_ms: int) -> int:
    if ttl_ms == 0:
        return ttl_ms
    if ttl_ms < TTL_MIN_MS:
        raise CoderError("ttl_ms must be 0 or at least 60000.")
    if ttl_ms > TTL_MAX_MS:
        raise CoderError("ttl_ms must be less than or equal to 2592000000.")
    return ttl_ms



def cmd_set_ttl(args: argparse.Namespace) -> int:
    workspace_id = validate_workspace_id(args.workspace_id)
    ttl_ms = validate_ttl_ms(args.ttl_ms)

    client = CoderClient(load_config())
    client.update_workspace_ttl(workspace_id, ttl_ms, dry_run=args.dry_run)

    if args.dry_run:
        print(
            f"Dry run: would update workspace {workspace_id} to "
            f"ttl_ms={ttl_ms}."
        )
        return 0

    updated_workspace = client.get_workspace(workspace_id)
    effective_ttl_ms = updated_workspace.get("ttl_ms")
    effective_ttl = format_ttl(effective_ttl_ms)
    if effective_ttl_ms is None:
        effective_ttl = "disabled"

    print(
        f"Updated workspace {workspace_id} to ttl_ms={effective_ttl_ms} "
        f"({effective_ttl})."
    )
    return 0



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit Coder workspaces and update workspace TTLs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    report_parser = subparsers.add_parser(
        "report",
        help="Show workspace status, audit-derived last start time, and TTL data.",
    )
    report_parser.add_argument(
        "--include-stopped",
        action="store_true",
        help="Include non-running workspaces in the report.",
    )
    report_parser.add_argument(
        "--owner",
        help="Filter by owner name substring.",
    )
    report_parser.add_argument(
        "--workspace",
        help="Filter by workspace name substring.",
    )
    report_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a table.",
    )
    report_parser.set_defaults(func=cmd_report)

    set_ttl_parser = subparsers.add_parser(
        "set-ttl",
        help="Update a workspace TTL by workspace ID.",
    )
    set_ttl_parser.add_argument("workspace_id", help="Workspace UUID.")
    set_ttl_parser.add_argument(
        "ttl_ms",
        type=int,
        help="TTL in milliseconds. Use 0 if your deployment treats that as disabled.",
    )
    set_ttl_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without calling the API.",
    )
    set_ttl_parser.set_defaults(func=cmd_set_ttl)

    return parser



def normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return ["report"]
    if argv[0] == "--set-ttl":
        return ["set-ttl", *argv[1:]]
    if argv[0] in {"-h", "--help"}:
        return argv
    if argv[0].startswith("-"):
        return ["report", *argv]
    return argv



def main() -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_argv(sys.argv[1:]))

    try:
        return int(args.func(args))
    except requests.RequestException as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1
    except CoderError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
