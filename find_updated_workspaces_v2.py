import requests
import os
import argparse
import sys

# Configuration
CODER_URL = os.getenv("CODER_URL", "https://coder.example.com")
CODER_SESSION_TOKEN = os.getenv("CODER_SESSION_TOKEN")

def get_headers():
    return {
        "Coder-Session-Token": CODER_SESSION_TOKEN,
        "Content-Type": "application/json"
    }

def get_outdated_workspaces(filter_names=None):
    headers = get_headers()
    params = {"q": "outdated:true"}
    
    response = requests.get(f"{CODER_URL}/api/v2/workspaces", headers=headers, params=params)
    if response.status_code != 200:
        print(f"Error fetching workspaces: {response.status_code}")
        return []
        
    workspaces = response.json().get("workspaces", [])
    
    if filter_names:
        workspaces = [ws for ws in workspaces if ws['name'] in filter_names]
        
    return workspaces

def trigger_update(workspace):
    headers = get_headers()
    # The build needs the active version ID from the template
    template_version_id = workspace['template_active_version_id']
    workspace_id = workspace['id']
    
    payload = {
        "template_version_id": template_version_id,
        "transition": "start" # Ensuring the workspace starts/restarts with new template
    }
    
    url = f"{CODER_URL}/api/v2/workspaces/{workspace_id}/builds"
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 201:
        print(f"Successfully queued update for: {workspace['name']}")
    else:
        print(f"Failed to update {workspace['name']}: {response.status_code} - {response.text}")

def main():
    parser = argparse.ArgumentParser(description="Coder Workspace Update Auditor")
    parser.add_argument("--workspace", help="Comma-separated list of workspace names to target")
    parser.add_argument("--force-update", action="store_true", help="Trigger the POST build call to update workspaces")
    
    args = parser.parse_args()

    target_names = [n.strip() for n in args.workspace.split(",")] if args.workspace else None
    
    outdated = get_outdated_workspaces(target_names)
    
    if not outdated:
        print("No outdated workspaces found matching criteria.")
        return

    print(f"Found {len(outdated)} outdated workspaces.\n")

    for ws in outdated:
        print(f"Targeting: {ws['owner_name']}/{ws['name']} (Template: {ws['template_name']})")
        if args.force_update:
            trigger_update(ws)
        else:
            print(f"  [DRY RUN] Use --force-update to trigger build.")

if __name__ == "__main__":
    if not CODER_SESSION_TOKEN:
        print("Error: CODER_SESSION_TOKEN environment variable not set.")
        sys.exit(1)
    main()