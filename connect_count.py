#!/usr/bin/env python3
#
# Creates two distinct tables, total login/connect between two dates and a connect_count per user
#
import requests
import json
import datetime
import os
import argparse
from urllib.parse import urlencode
from prettytable import PrettyTable
from collections import defaultdict

# Get the API token from file or environment variable
def get_token():
    if os.path.exists("audit-token.txt"):
        with open("audit-token.txt", "r") as f:
            return f.read().strip()
    return os.environ.get("CODER_TOKEN")

def parse_args():
    parser = argparse.ArgumentParser(description='Count Coder connection events')
    parser.add_argument('--url', default=os.environ.get("CODER_URL", "https://rcoder.sal.za.net"),
                        help='Coder URL')
    parser.add_argument('--start', required=True, help='Start time (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End time (YYYY-MM-DD)')
    return parser.parse_args()

def get_connection_data(coder_url, token, start_date, end_date):
    """
    Retrieve and analyze connection events within a date range using the v2 API
    """
    headers = {
        'Accept': 'application/json',
        'Coder-Session-Token': token
    }

    # Convert dates to ISO format and add time boundaries
    start_iso = f"{start_date}T00:00:00Z"
    end_iso = f"{end_date}T23:59:59Z"
    
    # Track all actions
    action_counts = defaultdict(int)
    
    # Track login events by user
    login_counts = defaultdict(int)
    
    # Keep track of connections
    connection_count = 0
    after_id = None
    previous_after_id = None  # Track previous after_id to detect loops
    
    # In v2, we need to check multiple connection actions
    connection_actions = [
        'login',
        'start_workspace_connection',
        'start',
        'connect_workspace',
        'workspace_connection',
        'workspace.connect'  # Add more if needed
    ]
    
    all_logs = []
    
    while True:
        # Check if we're stuck in a loop
        if after_id == previous_after_id and after_id is not None:
            print(f"Breaking out of loop - same after_id encountered twice: {after_id}")
            break
            
        previous_after_id = after_id
        
        # Build params for fetching audit logs with filters
        params = {
            'limit': 100,                   # Fetch 100 records at a time
            'after_time': start_iso,        # Start of time range
            'before_time': end_iso,         # End of time range
        }
        
        # Add after_id parameter only if we have one
        if after_id:
            params['after_id'] = after_id
        
        # Make the API request
        url = f"{coder_url}/api/v2/audit"
        print(f"Fetching page from {url} with params: {params}")
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"Error fetching audit logs: {response.status_code}")
            print(response.text)
            break
        
        data = response.json()
        logs = data.get('audit_logs', [])
        
        # If we got no logs, we're done
        if not logs:
            print("No logs found in this batch")
            break
        
        # Process logs from this batch
        for log in logs:
            action = log.get('action')
            
            # Track all actions for the summary table
            action_counts[action] += 1
            
            # Check if this is a login action and track the user
            if action == 'login':
                user = log.get('user', {}).get('username', 'unknown')
                login_counts[user] += 1
            
            # Check if the action matches any of our connection actions
            if action in connection_actions:
                connection_count += 1
        
        print(f"Processed {len(logs)} logs in this batch")
        
        # Check if we need to fetch the next page
        if len(logs) < params['limit']:
            # We received fewer logs than the limit, so we're at the end
            print("Received fewer logs than requested limit - reached the end of data")
            break
            
        # Use the ID of the last log as the after_id for the next request
        after_id = logs[-1].get('id')
        print(f"Next page after_id: {after_id}")
    
    return connection_count, action_counts, login_counts

def display_tables(action_counts, login_counts, connection_count, start_date, end_date):
    # Display action summary table
    action_table = PrettyTable()
    action_table.field_names = ["Action", "Count"]
    action_table.align["Action"] = "l"
    action_table.align["Count"] = "r"
    
    for action, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True):
        action_table.add_row([action, count])
    
    print("\n=== Action Summary ===")
    print(action_table)
    
    # Display login summary table
    login_table = PrettyTable()
    login_table.field_names = ["User", "Login Count"]
    login_table.align["User"] = "l"
    login_table.align["Login Count"] = "r"
    
    for user, count in sorted(login_counts.items(), key=lambda x: x[1], reverse=True):
        login_table.add_row([user, count])
    
    print("\n=== Login Summary ===")
    print(login_table)
    
    # Display total connection count
    print(f"\nTotal connection count between {start_date} and {end_date}: {connection_count}")

def main():
    args = parse_args()
    token = get_token()
    
    if not token:
        print("Error: No Coder token found. Set CODER_TOKEN environment variable or create audit-token.txt file.")
        return
    
    connection_count, action_counts, login_counts = get_connection_data(args.url, token, args.start, args.end)
    
    display_tables(action_counts, login_counts, connection_count, args.start, args.end)

if __name__ == "__main__":
    main()
