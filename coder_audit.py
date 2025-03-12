#!/usr/bin/env python3

import requests
import json
import datetime
import os
from tabulate import tabulate

# Get the API token from file or environment variable
def get_token():
    if os.path.exists("audit-token.txt"):
        with open("audit-token.txt", "r") as f:
            return f.read().strip()
    return os.environ.get("CODER_TOKEN")

FQDN="My URL"
# Add your token to audit-token.txt or update here
CODER_URL = f"https://{FQDN}"
TOKEN = get_token()

headers = {
    'Accept': 'application/json',
    'Coder-Session-Token': TOKEN
}

def get_audit_logs():
    """Fetch audit logs from Coder API"""
    url = f"{CODER_URL}/api/v2/audit?limit=0"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["audit_logs"]
    else:
        print(f"Error fetching audit logs: {response.status_code}")
        return []

def get_workspaces():
    """Fetch workspaces from Coder API"""
    url = f"{CODER_URL}/api/v2/workspaces"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["workspaces"]
    else:
        print(f"Error fetching workspaces: {response.status_code}")
        return []

def format_date(date_str):
    """Format date string to a more readable format"""
    if not date_str or date_str == "0001-01-01T00:00:00Z":
        return "N/A"
    try:
        dt = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return date_str

def format_ttl(ms):
    """Format TTL from milliseconds to a human-readable format"""
    if not ms:
        return "N/A"
    
    seconds = ms / 1000000000
    hours = seconds / 3600
    
    if hours < 1:
        return f"{int(seconds)} seconds"
    elif hours < 24:
        return f"{int(hours)} hours"
    else:
        days = hours / 24
        return f"{int(days)} days"

def main():
    # Get data
    audit_logs = get_audit_logs()
    workspaces = get_workspaces()
    
    # Create a dict to map workspace id to workspace info
    workspace_map = {ws['id']: ws for ws in workspaces}
    
    # Prepare data for display
    table_data = []
    
    for workspace in workspaces:
        if workspace['latest_build']['status'] == 'running':
            username = workspace['owner_name']
            workspace_name = workspace['name']
            status = workspace['latest_build']['status']
            last_seen = format_date(workspace['owner'].get('last_seen_at', 'N/A') if 'owner' in workspace else workspace.get('last_used_at', 'N/A'))
            ttl = format_ttl(workspace.get('ttl_ms'))
            deadline = format_date(workspace['latest_build'].get('deadline', 'N/A'))
            max_deadline = format_date(workspace['latest_build'].get('max_deadline', 'N/A'))
            
            table_data.append([
                username,
                workspace_name,
                status,
                last_seen,
                ttl,
                deadline,
                max_deadline
            ])
    
    # Sort by username, then workspace name
    table_data.sort(key=lambda x: (x[0].lower(), x[1].lower()))
    
    # Display the table
    headers = ["Username", "Workspace", "Status", "Last Seen", "TTL", "Deadline", "Max Deadline"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

if __name__ == "__main__":
    main()

