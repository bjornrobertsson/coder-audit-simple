#!/usr/bin/env python3
#
# Allows query of Workspaces and ttl_ms change with parameters
# 

import json
import requests
import sys
from datetime import datetime
import pprint

def get_audit_logs(token):
    url = "https://rcoder.sal.za.net/api/v2/audit?limit=0"
    headers = {
        'Accept': 'application/json',
        'Coder-Session-Token': token
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error retrieving audit logs: {response.status_code}")
        sys.exit(1)

    return response.json()

def format_time(time_str):
    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def get_workspace_ttl(token, workspace_id):
    url = f"https://rcoder.sal.za.net/api/v2/workspaces/{workspace_id}"
    headers = {
        'Accept': 'application/json',
        'Coder-Session-Token': token
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get('ttl_ms', None)
    else:
        return None

def extract_workspace_activity(token,logs):
    workspace_activities = []

    for log in logs.get('audit_logs', []):
        # pprint.pprint(log)
        # break  # Only print the first one for brevity

        if (log.get('resource_type') == 'workspace_build' and
            log.get('action') == 'start'):

            username = log.get('user', {}).get('username')
            workspace_name = log.get('additional_fields', {}).get('workspace_name', 'N/A')
            ## workspace_id = log.get('resource_target', 'N/A')
            workspace_id = log.get('additional_fields', {}).get('workspace_id', 'N/A')

            start_time = format_time(log.get('time', ''))
            ttl_ms = get_workspace_ttl(token,workspace_id)


            workspace_activities.append({
                'username': username,
                'workspace_name': workspace_name,
                'workspace_id': workspace_id,
                'start_time': start_time,
                'ttl_ms': ttl_ms

            })

    return workspace_activities

def update_workspace_ttl(token, workspace_id, ttl_ms):
    url = f"https://rcoder.sal.za.net/api/v2/workspaces/{workspace_id}/ttl"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Coder-Session-Token': token
    }
    payload = {
        "ttl_ms": ttl_ms
    }

    response = requests.put(url, headers=headers, data=json.dumps(payload))
    if response.status_code in (200, 204):
        print(f"Successfully updated TTL for workspace {workspace_id} to {ttl_ms} ms.")
    else:
        print(f"Failed to update TTL: {response.status_code} - {response.text}")
        sys.exit(1)

def main():
    try:
        with open('audit-token.txt', 'r') as f:
            token = f.read().strip()

        if len(sys.argv) == 4 and sys.argv[1] == '--set-ttl':
            workspace_id = sys.argv[2]
            ttl_ms = int(sys.argv[3])
            update_workspace_ttl(token, workspace_id, ttl_ms)
            return

        logs = get_audit_logs(token)
        activities = extract_workspace_activity(token,logs)

        print("\nWorkspace Activity Report:")
        print("-" * 135)
        print(f"{'Username':<15} {'Workspace Name':<25} {'Workspace ID':<40} {'Start Time':<25} {'TTL (ms)':<15}")
        print("-" * 135)

        for activity in activities:
            print(f"{activity['username'] or 'N/A':<15} "
                  f"{activity['workspace_name']:<25} "
                  f"{activity['workspace_id']:<40} "
                  f"{activity['start_time']:<25} "
                  f"{activity['ttl_ms'] if activity['ttl_ms'] is not None else 'N/A':<15}")


        print(f"\nTotal workspace start events found: {len(activities)}")

    except FileNotFoundError:
        print("Error: audit-token.txt file not found")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Invalid JSON response from API")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
