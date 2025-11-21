#!/usr/bin/env python3
"""
Coder Activity Dashboard

Provides comprehensive activity information using Coder's insights API endpoints:
- /api/v2/insights/user-status-counts
- /api/v2/workspaces/{workspace}
- /api/v2/insights/user-activity
"""

import requests
import json
import datetime
from datetime import timezone, timedelta
import os
import sys
from tabulate import tabulate
from urllib.parse import quote

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
    return "FQDN"

FQDN = get_fqdn()
CODER_URL = f"{FQDN}"
TOKEN = get_token()

headers = {
    'Accept': 'application/json',
    'Coder-Session-Token': TOKEN
}

def get_user_status_counts():
    """Get user status counts from insights API"""
    url = f"{CODER_URL}/api/v2/insights/user-status-counts"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching user status counts: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error connecting to user status counts API: {e}")
        return None

def get_all_workspaces():
    """Get all workspaces from the API"""
    url = f"{CODER_URL}/api/v2/workspaces"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("workspaces", [])
        else:
            print(f"Error fetching workspaces: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error connecting to workspaces API: {e}")
        return []

def get_workspace_details(workspace_id):
    """Get detailed information about a specific workspace"""
    url = f"{CODER_URL}/api/v2/workspaces/{workspace_id}"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching workspace {workspace_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error connecting to workspace API: {e}")
        return None

def get_user_activity(start_date=None, end_date=None):
    """Get user activity from insights API"""
    if not start_date:
        start_date = (datetime.datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    if not end_date:
        end_date = datetime.datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # URL encode the date parameters
    start_encoded = quote(start_date)
    end_encoded = quote(end_date)
    
    url = f"{CODER_URL}/api/v2/insights/user-activity?start_time={start_encoded}&end_time={end_encoded}"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching user activity: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error connecting to user activity API: {e}")
        return None

def get_templates():
    """Fetch templates from Coder API"""
    url = f"{CODER_URL}/api/v2/templates"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching templates: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error connecting to templates API: {e}")
        return []

def format_time_remaining(deadline):
    """Format time remaining until workspace stops"""
    if not deadline or deadline == "N/A":
        return "N/A"
    
    try:
        dt = datetime.datetime.fromisoformat(deadline.replace('Z', '+00:00'))
        now = datetime.datetime.now(timezone.utc)
        remaining = dt - now
        
        if remaining.total_seconds() < 0:
            return "Expired"
        
        days = remaining.days
        hours, remainder = divmod(remaining.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    except:
        return "Invalid"

def format_ttl(ms):
    """Format TTL from milliseconds to human-readable format"""
    if not ms:
        return "N/A"
    
    seconds = ms / 1000
    
    if seconds < 60:
        return f"{int(seconds)}s"
    
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)}m"
    
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}h"
    
    days = hours / 24
    return f"{int(days)}d"

def format_date(date_str):
    """Format date string to readable format"""
    if not date_str or date_str == "0001-01-01T00:00:00Z":
        return "N/A"
    try:
        dt = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return date_str

def display_user_status_summary():
    """Display user status summary"""
    print("\n" + "="*80)
    print("CODER ACTIVITY DASHBOARD")
    print("="*80)
    
    status_counts = get_user_status_counts()
    if status_counts:
        print("\n📊 USER STATUS SUMMARY:")
        print("-" * 40)
        
        # Display status counts
        status_table = []
        for status, count in status_counts.items():
            status_table.append([status.replace('_', ' ').title(), count])
        
        if status_table:
            print(tabulate(status_table, headers=["Status", "Count"], tablefmt="simple"))
        else:
            print("No status data available")
    else:
        print("❌ Could not fetch user status counts")

def display_workspace_summary():
    """Display workspace summary"""
    print("\n\n💻 WORKSPACE SUMMARY:")
    print("-" * 40)
    
    workspaces = get_all_workspaces()
    templates = get_templates()
    template_map = {tpl['id']: tpl['name'] for tpl in templates}
    
    if not workspaces:
        print("No workspaces found")
        return
    
    # Count workspaces by status
    status_counts = {}
    template_counts = {}
    
    workspace_table = []
    
    for ws in workspaces:
        status = ws.get('latest_build', {}).get('status', 'unknown')
        template_id = ws.get('template_id')
        template_name = template_map.get(template_id, 'Unknown')
        
        status_counts[status] = status_counts.get(status, 0) + 1
        template_counts[template_name] = template_counts.get(template_name, 0) + 1
        
        # Only show running workspaces in detail
        if status == 'running':
            owner = ws.get('owner_name', 'Unknown')
            name = ws.get('name', 'Unknown')
            ttl = format_ttl(ws.get('ttl_ms'))
            deadline = ws.get('latest_build', {}).get('deadline')
            until_stop = format_time_remaining(deadline)
            
            workspace_table.append([
                owner,
                name,
                template_name,
                status,
                ttl,
                until_stop
            ])
    
    # Display status summary
    print("Status Distribution:")
    status_summary = [[status.title(), count] for status, count in status_counts.items()]
    print(tabulate(status_summary, headers=["Status", "Count"], tablefmt="simple"))
    
    print("\nTemplate Distribution:")
    template_summary = [[template, count] for template, count in template_counts.items()]
    print(tabulate(template_summary, headers=["Template", "Count"], tablefmt="simple"))
    
    # Display running workspaces in detail
    if workspace_table:
        print("\n🟢 RUNNING WORKSPACES:")
        print("-" * 40)
        workspace_table.sort(key=lambda x: (x[0].lower(), x[1].lower()))
        headers = ["Owner", "Workspace", "Template", "Status", "TTL", "Until Stop"]
        print(tabulate(workspace_table, headers=headers, tablefmt="grid"))
    else:
        print("\n✅ No running workspaces found")

def display_user_activity():
    """Display user activity information"""
    print("\n\n📈 USER ACTIVITY (Last 30 Days):")
    print("-" * 40)
    
    # Try different date ranges to see if we get data
    date_ranges = [
        (30, "Last 30 Days"),
        (7, "Last 7 Days"),
        (1, "Last 24 Hours")
    ]
    
    for days, label in date_ranges:
        start_date = (datetime.datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end_date = datetime.datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        activity_data = get_user_activity(start_date, end_date)
        
        if activity_data and activity_data.get('report', {}).get('users'):
            print(f"\n{label}:")
            users = activity_data['report']['users']
            
            activity_table = []
            for user in users:
                username = user.get('username', 'Unknown')
                activity_table.append([username, "Active"])
            
            if activity_table:
                print(tabulate(activity_table, headers=["Username", "Activity"], tablefmt="simple"))
            break
        else:
            print(f"No activity data for {label.lower()}")
    else:
        print("❌ No user activity data available for any time range")
        print("This might indicate:")
        print("  • No user activity in the specified periods")
        print("  • Insufficient permissions to access activity data")
        print("  • Activity tracking may not be enabled")

def main():
    """Main dashboard function"""
    try:
        display_user_status_summary()
        display_workspace_summary()
        display_user_activity()
        
        print("\n" + "="*80)
        print(f"Dashboard updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Dashboard interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error generating dashboard: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
