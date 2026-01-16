#!/usr/bin/env python3
"""
Coder Organization Workspace Sorter

Collects Organizations in the Coder Deployment, lists Workspaces for each,
and sorts them by last used/stopped time.
"""

import requests
import json
import datetime
import os
import sys
from tabulate import tabulate

# Configuration
def get_token():
    if os.path.exists("audit-token.txt"):
        with open("audit-token.txt", "r") as f:
            return f.read().strip()
    return os.environ.get("CODER_TOKEN")

def get_fqdn():
    if os.environ.get("CODER_URL"):
        return os.environ.get("CODER_URL")
    print("Use CODER_URL ENV to pass your FQDN")
    # Fallback to avoid immediate crash if just testing logic, 
    # but strictly it should be provided.
    return "http://localhost:3000"

FQDN = get_fqdn()
CODER_URL = f"{FQDN}"
TOKEN = get_token()

headers = {
    'Accept': 'application/json',
    'Coder-Session-Token': TOKEN
}

def get_organizations():
    """Fetch all organizations from Coder API"""
    url = f"{CODER_URL}/api/v2/organizations"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching organizations: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"Error connecting to organizations API: {e}")
        return []

def get_workspaces():
    """Fetch all workspaces from Coder API"""
    # Fetching all workspaces. In a very large deployment, pagination might be needed.
    # The default limit is often 20 or 25. We set limit=0 (if supported) or a high number.
    # Coder API usually supports ?limit= and ?offset=. 
    # For this script, we'll try a reasonably high limit.
    url = f"{CODER_URL}/api/v2/workspaces?limit=1000" 
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            # Handle both list (older API) and dict with 'workspaces' key (newer API)
            if isinstance(data, list):
                return data
            return data.get("workspaces", [])
        else:
            print(f"Error fetching workspaces: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"Error connecting to workspaces API: {e}")
        return []

def parse_time(time_str):
    """Parse a time string into a datetime object for sorting"""
    if not time_str or time_str == "0001-01-01T00:00:00Z":
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    try:
        return datetime.datetime.fromisoformat(time_str.replace('Z', '+00:00'))
    except ValueError:
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

def format_date(date_str):
    """Format date string to a more readable format"""
    if not date_str or date_str == "0001-01-01T00:00:00Z":
        return "Never"
    try:
        dt = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return date_str

def main():
    if not TOKEN:
        print("Error: No authentication token found. Please set CODER_TOKEN env var or create audit-token.txt.")
        sys.exit(1)

    print(f"Connecting to {CODER_URL}...")

    # 1. Collect Organizations
    organizations = get_organizations()
    if not organizations:
        print("No organizations found or failed to fetch organizations.")
        # Proceeding might be possible if we just list workspaces, but request was specific.
        # We will try to proceed by grouping workspaces by their org_id even if we don't have org names.
    
    org_map = {org['id']: org['name'] for org in organizations}
    
    # 2. Collect Workspaces
    workspaces = get_workspaces()
    if not workspaces:
        print("No workspaces found.")
        sys.exit(0)

    # 3. Group Workspaces by Organization
    # structure: { org_id: [workspace1, workspace2, ...] }
    workspaces_by_org = {}
    
    for ws in workspaces:
        org_id = ws.get('organization_id', 'Unknown')
        if org_id not in workspaces_by_org:
            workspaces_by_org[org_id] = []
        workspaces_by_org[org_id].append(ws)

    # 4. Sort and Display
    print("\n" + "="*80)
    print("WORKSPACES BY ORGANIZATION (Sorted by Last Used/Stopped)")
    print("="*80)

    # Iterate through organizations found in API, plus any 'Unknown' found in workspaces
    all_org_ids = list(org_map.keys())
    for org_id in workspaces_by_org.keys():
        if org_id not in all_org_ids:
            all_org_ids.append(org_id)

    for org_id in all_org_ids:
        org_name = org_map.get(org_id, f"Unknown Org ({org_id})")
        org_workspaces = workspaces_by_org.get(org_id, [])

        if not org_workspaces:
            # Optional: Skip empty organizations? 
            # The user asked to "list Workspaces based on the Organisation", 
            # implies listing the Org even if empty? 
            # Let's show it to be complete.
            print(f"\nOrganization: {org_name}")
            print("  (No workspaces)")
            continue

        # Sort workspaces
        # Primary key: last_used_at
        # Secondary key: created_at (as tie breaker)
        # We want DESCENDING order (newest first)
        def sort_key(ws):
            last_used = ws.get('last_used_at')
            # If last_used is null, check if it's running? 
            # Or use created_at? 
            # If it's never used, it should probably be last.
            return parse_time(last_used)

        org_workspaces.sort(key=sort_key, reverse=True)

        print(f"\nOrganization: {org_name}")
        
        table_data = []
        headers = ["Workspace", "Owner", "Status", "Last Used", "Created"]

        for ws in org_workspaces:
            name = ws.get('name', 'N/A')
            owner = ws.get('owner_name', 'N/A')
            status = ws.get('latest_build', {}).get('status', 'N/A')
            last_used_raw = ws.get('last_used_at')
            created_raw = ws.get('created_at')
            
            last_used_fmt = format_date(last_used_raw)
            created_fmt = format_date(created_raw)

            table_data.append([name, owner, status, last_used_fmt, created_fmt])

        print(tabulate(table_data, headers=headers, tablefmt="simple"))

if __name__ == "__main__":
    main()
