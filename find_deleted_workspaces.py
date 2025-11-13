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

import datetime

def get_audit_logs():
    """Fetch audit logs from Coder API"""
    url = f"{CODER_URL}/api/v2/audit?limit=0"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["audit_logs"]
    else:
        print(f"Error fetching audit logs: {response.status_code}")
        return []

def get_users():
    """Fetch users from Coder API"""
    url = f"{CODER_URL}/api/v2/users"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["users"]
    else:
        print(f"Error fetching users: {response.status_code}")
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

def main():
    audit_logs = get_audit_logs()
    users = get_users()
    
    deleted_by_user = {user['username']: [] for user in users}

    if audit_logs:
        for log in audit_logs:
            if log.get('action') == 'delete' and log.get('resource_type') in ['workspace', 'workspace_build']:
                workspace_name = log.get('additional_fields', {}).get('workspace_name')
                if not workspace_name:
                    workspace_name = log.get('resource_target')
                
                user = log.get('user', {}).get('username')
                time = log.get('time')

                if workspace_name and user and time:
                    if user in deleted_by_user:
                        deleted_by_user[user].append({
                            "name": workspace_name,
                            "time": format_date(time)
                        })

    print("Deleted workspaces by user:")
    for user, workspaces in deleted_by_user.items():
        print(f"\nUser: {user}")
        if workspaces:
            for ws in workspaces:
                print(f"- {ws['name']} (at {ws['time']})")
        else:
            print("- No deleted workspaces found.")

if __name__ == "__main__":
    main()
