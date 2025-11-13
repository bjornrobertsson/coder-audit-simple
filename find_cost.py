#!/usr/bin/env python3

import requests
import os

# Get the API token from file or environment variable
def get_token():
    if os.path.exists("audit-token.txt"):
        with open("audit-token.txt", "r") as f:
            return f.read().strip()
    return os.environ.get("CODER_TOKEN")

def get_fqdn():
    if os.environ.get("CODER_URL"):
      return os.environ.get("CODER_URL")
    print("Use CODER_URL ENV to pass your FQDN")
    return "FQDN"


FQDN = get_fqdn()
CODER_URL = f"https://{FQDN}"
TOKEN = get_token()

headers = {
    'Accept': 'application/json',
    'Coder-Session-Token': TOKEN
}

import argparse
import json

def get_workspaces():
    """Fetch workspaces from Coder API"""
    url = f"{CODER_URL}/api/v2/workspaces"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["workspaces"]
    else:
        print(f"Error fetching workspaces: {response.status_code}")
        return []

def get_workspace_by_id(workspace_id):
    """Fetch a single workspace by its ID from the Coder API"""
    url = f"{CODER_URL}/api/v2/workspaces/{workspace_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return None

def get_audit_logs():
    """Fetch audit logs from Coder API"""
    url = f"{CODER_URL}/api/v2/audit?limit=0"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["audit_logs"]
    else:
        print(f"Error fetching audit logs: {response.status_code}")
        return []

def main():
    parser = argparse.ArgumentParser(description="Find workspace costs.")
    parser.add_argument('--deleted', action='store_true', help='Find costs for deleted workspaces.')
    args = parser.parse_args()

    if args.deleted:
        print("Finding costs for deleted workspaces...")
        audit_logs = get_audit_logs()
        if not audit_logs:
            print("No audit logs found.")
            return

        deleted_workspaces = []
        for log in audit_logs:
            if log.get('action') == 'delete' and log.get('resource_type') in ['workspace', 'workspace_build']:
                workspace_id = log.get('additional_fields', {}).get('workspace_id')
                workspace_name = log.get('additional_fields', {}).get('workspace_name')
                if not workspace_name:
                    workspace_name = log.get('resource_target')

                if workspace_id and workspace_name:
                    deleted_workspaces.append({'id': workspace_id, 'name': workspace_name})

        if deleted_workspaces:
            print("Deleted Workspace Costs:")
            for ws_info in deleted_workspaces:
                workspace = get_workspace_by_id(ws_info['id'])
                if workspace:
                    cost = workspace.get('latest_build', {}).get('daily_cost')
                    template_name = workspace.get('template_name')
                    template_display_name = workspace.get('template_display_name')
                    print(f"- {ws_info['name']}: ${cost:.2f} per day (Template: {template_name} - {template_display_name})")
                else:
                    print(f"- {ws_info['name']}: Cost information not available (workspace permanently deleted).")
        else:
            print("No deleted workspaces found in audit logs.")

    else:
        workspaces = get_workspaces()
        
        if workspaces:
            print("Workspace Costs:")
            for workspace in workspaces:
                name = workspace.get('name')
                cost = workspace.get('latest_build', {}).get('daily_cost')
                template_name = workspace.get('template_name')
                template_display_name = workspace.get('template_display_name')
                if name and cost is not None:
                    print(f"- {name}: ${cost:.2f} per day (Template: {template_name} - {template_display_name})")
        else:
            print("No workspaces found.")

if __name__ == "__main__":
    main()
