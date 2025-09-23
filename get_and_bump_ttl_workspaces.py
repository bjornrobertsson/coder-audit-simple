#!/usr/bin/env python3
#
# Allows query of Workspaces and ttl_ms change with parameters
# 

import json
import requests
import sys
import os
from datetime import datetime, timedelta, timezone
import pprint

# Get the API token from file or environment variable
def get_token():
    if os.path.exists("audit-token.txt"):
        with open("audit-token.txt", "r") as f:
            return f.read().strip()
    token = os.environ.get("CODER_TOKEN")
    if token:
        return token
    print("You must provide a CODER_TOKEN or audit-token.txt")
    sys.exit(1)

def get_fqdn():
    if os.environ.get("CODER_URL"):
        return os.environ.get("CODER_URL")
    print("Use CODER_URL ENV to pass your FQDN")
    sys.exit(1)

# Get configuration
FQDN = get_fqdn()
CODER_URL = f"https://{FQDN}"
TOKEN = get_token()

headers = {
    'Accept': 'application/json',
    'Coder-Session-Token': TOKEN
}

def get_audit_logs(token):
    url = f"{CODER_URL}/api/v2/audit?limit=0"

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error retrieving audit logs: {response.status_code}")
        sys.exit(1)

    return response.json()

def format_time(time_str):
    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def format_time_remaining(remaining_seconds):
    """Format time remaining in human-readable format like '1d', '1h', '1h2m'"""
    if remaining_seconds <= 0:
        return None
    
    days = int(remaining_seconds // 86400)
    hours = int((remaining_seconds % 86400) // 3600)
    minutes = int((remaining_seconds % 3600) // 60)
    
    if days > 0:
        if hours > 0:
            return f"{days}d{hours}h"
        else:
            return f"{days}d"
    elif hours > 0:
        if minutes > 0:
            return f"{hours}h{minutes}m"
        else:
            return f"{hours}h"
    else:
        return f"{minutes}m"

def get_templates(token):
    """Fetch templates from Coder API"""
    url = f"{CODER_URL}/api/v2/templates"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        # API returns a list directly, not an object with "templates" key
        return response.json()
    else:
        print(f"Error fetching templates: {response.status_code}")
        return []

def get_workspace_details(token, workspace_id):
    """Get workspace details including template_id, ttl_ms, deadline, and status"""
    url = f"{CODER_URL}/api/v2/workspaces/{workspace_id}"

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return {
            'ttl_ms': data.get('ttl_ms', None),
            'template_id': data.get('template_id', None),
            'deadline': data.get('latest_build', {}).get('deadline', None),
            'status': data.get('latest_build', {}).get('status', None)
        }
    else:
        return {'ttl_ms': None, 'template_id': None, 'deadline': None, 'status': None}

def extract_workspace_activity(token, logs, template_map):
    workspace_activities = []
    workspace_latest = {}  # Track the latest start time for each workspace

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
            log_time = log.get('time', '')
            
            # Only keep the latest start event for each workspace
            if workspace_id not in workspace_latest or log_time > workspace_latest[workspace_id]['log_time']:
                workspace_details = get_workspace_details(token, workspace_id)
                ttl_ms = workspace_details['ttl_ms']
                template_id = workspace_details['template_id']
                template_name = template_map.get(template_id, 'Unknown') if template_id else 'N/A'
                
                # Calculate until_stop time using workspace deadline (only for running workspaces)
                until_stop = None
                try:
                    # Only show until_stop for currently running workspaces
                    if workspace_details['status'] == 'running':
                        deadline_str = workspace_details['deadline']
                        if deadline_str:
                            deadline_dt = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
                            now = datetime.now(timezone.utc)
                            
                            if deadline_dt > now:
                                remaining_seconds = (deadline_dt - now).total_seconds()
                                until_stop = format_time_remaining(remaining_seconds)
                except Exception:
                    until_stop = None

                workspace_latest[workspace_id] = {
                    'username': username,
                    'workspace_name': workspace_name,
                    'workspace_id': workspace_id,
                    'start_time': start_time,
                    'log_time': log_time,
                    'ttl_ms': ttl_ms,
                    'template_name': template_name,
                    'until_stop': until_stop
                }

    # Convert dictionary values to list
    return list(workspace_latest.values())

def update_workspace_ttl(token, workspace_id, ttl_ms):
    url = f"{CODER_URL}/api/v2/workspaces/{workspace_id}/ttl"
    # Extend global headers with Content-Type for PUT request
    put_headers = {**headers, 'Content-Type': 'application/json'}
    payload = {
        "ttl_ms": ttl_ms
    }

    response = requests.put(url, headers=put_headers, data=json.dumps(payload))
    if response.status_code in (200, 204):
        print(f"Successfully updated TTL for workspace {workspace_id} to {ttl_ms} ms.")
    else:
        print(f"Failed to update TTL: {response.status_code} - {response.text}")
        sys.exit(1)

def main():
    try:
        token = get_token()

        if len(sys.argv) == 4 and sys.argv[1] == '--set-ttl':
            workspace_id = sys.argv[2]
            ttl_ms = int(sys.argv[3])
            update_workspace_ttl(token, workspace_id, ttl_ms)
            return

        logs = get_audit_logs(token)
        templates = get_templates(token)
        
        # Create a dict to map template id to template name
        template_map = {tpl['id']: tpl['name'] for tpl in templates}
        
        activities = extract_workspace_activity(token, logs, template_map)

        print("\nWorkspace Activity Report:")
        print("-" * 180)
        print(f"{'Username':<15} {'Workspace Name':<25} {'Template':<20} {'Workspace ID':<40} {'Start Time':<25} {'TTL (ms)':<15} {'Until Stop':<10}")
        print("-" * 180)

        for activity in activities:
            until_stop_str = activity['until_stop'] if activity['until_stop'] else ''
            print(f"{activity['username'] or 'N/A':<15} "
                  f"{activity['workspace_name']:<25} "
                  f"{activity['template_name']:<20} "
                  f"{activity['workspace_id']:<40} "
                  f"{activity['start_time']:<25} "
                  f"{activity['ttl_ms'] if activity['ttl_ms'] is not None else 'N/A':<15} "
                  f"{until_stop_str:<10}")

        print(f"\nTotal workspace start events found: {len(activities)}")

    except json.JSONDecodeError:
        print("Error: Invalid JSON response from API")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
