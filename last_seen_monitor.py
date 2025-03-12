#!/usr/bin/env python3
import json
import sys
import requests
from datetime import datetime
import os
from tabulate import tabulate

FQDN="My URL"
# Add audit-token.txt or manually in this script

def get_audit_logs(token, url=f"https://{FQDN}/api/v2/audit", limit=0):
    """Fetch audit logs from the Coder API"""
    headers = {
        'Accept': 'application/json',
        'Coder-Session-Token': token
    }
    params = {'limit': limit}
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Error fetching audit logs: {response.status_code}")
        sys.exit(1)
    
    return response.json()

def format_datetime(datetime_str):
    """Format datetime string to a more readable format"""
    try:
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return datetime_str

def format_time_delta(seconds):
    """Format time in seconds to human readable format"""
    if seconds == 0:
        return "N/A"
        
    hours = seconds // 3600
    days = hours // 24
    hours = hours % 24
    
    if days > 0:
        return f"{days}d {hours}h"
    else:
        return f"{hours}h"

def process_audit_logs(logs):
    """Process the audit logs and extract relevant information"""
    results = []
    
    for log in logs["audit_logs"]:
        # Include all entries that have user information
        if "user" in log and log["user"]:
            username = log["user"].get("username", "")
            last_seen_at = format_datetime(log["user"].get("last_seen_at", ""))
            status = log["user"].get("status", "")
            
            # For workspace related actions, get workspace name
            workspace_name = ""
            if "additional_fields" in log and "workspace_name" in log["additional_fields"]:
                workspace_name = log["additional_fields"]["workspace_name"]
            
            # Get the action time
            action_time = format_datetime(log.get("time", ""))
            
            # Look for activity_bump in relevant entries
            activity_bump = "N/A"
            if log["resource_type"] == "template" and "diff" in log and "activity_bump" in log["diff"]:
                activity_seconds = log["diff"]["activity_bump"].get("new", 0) / 1000000000
                activity_bump = format_time_delta(activity_seconds)
            
            results.append([
                username,
                workspace_name, 
                action_time,
                activity_bump,
                last_seen_at,
                status
            ])
    
    return results

def main():
    # Get the token from file
    try:
        with open("audit-token.txt", "r") as f:
            token = f.read().strip()
    except:
        print("Error reading token from audit-token.txt")
        sys.exit(1)
    
    # Fetch the audit logs
    logs = get_audit_logs(token)
    
    # Process the logs
    results = process_audit_logs(logs)
    
    # Display results in a table
    headers = ["Username", "Workspace Name", "Action Time", "Activity Bump", "Last Seen At", "Status"]
    print(tabulate(results, headers=headers, tablefmt="pretty"))
    
    print(f"\nTotal entries: {len(results)}")

if __name__ == "__main__":
    main()
