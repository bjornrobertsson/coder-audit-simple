#!/usr/bin/env python3
"""
Coder Last - Emulates Unix/Linux 'last' command for Coder audit logs
Shows recent user login/logout activities from Coder audit logs
"""

import requests
import json
import sys
import argparse
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class CoderLast:
    def __init__(self, coder_url: str, token: str):
        self.coder_url = coder_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            'Coder-Session-Token': token,
            'Accept': 'application/json'
        })
    
    def get_audit_logs(self, limit: int = 100, q: str = "") -> List[Dict]:
        """Fetch audit logs from Coder API"""
        url = f"{self.coder_url}/api/v2/audit"
        params = {
            'limit': limit
        }
        if q:
            params['q'] = q
            
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('audit_logs', [])
        except requests.RequestException as e:
            print(f"Error fetching audit logs: {e}", file=sys.stderr)
            return []
    
    def format_duration(self, start_time: str, end_time: Optional[str] = None) -> str:
        """Format session duration like Unix last command"""
        try:
            start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            if end_time:
                end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                duration = end - start
                hours = int(duration.total_seconds() // 3600)
                minutes = int((duration.total_seconds() % 3600) // 60)
                return f"({hours:02d}:{minutes:02d})"
            else:
                return "still logged in"
        except:
            return "unknown"
    
    def get_user_sessions(self, username: str = None, limit: int = 50) -> List[Dict]:
        """Get user login/logout sessions from audit logs"""
        # First, try to get workspace build events (these represent user activity)
        query_parts = ["resource_type:workspace_build"]
        
        if username:
            query_parts.append(f"username:{username}")
        
        query = " ".join(query_parts)
        
        logs = self.get_audit_logs(limit=limit * 2, q=query)
        
        # Process logs to extract session information
        sessions = []
        user_sessions = {}  # Track ongoing sessions per user
        
        # Sort logs chronologically (oldest first for processing)
        sorted_logs = sorted(logs, key=lambda x: x.get('time', ''))
        
        for log in sorted_logs:
            user = log.get('user', {}).get('username', 'unknown')
            action = log.get('action', '')
            time_str = log.get('time', '')
            resource_type = log.get('resource_type', '')
            ip = log.get('ip', '')
            resource_target = log.get('resource_target', '')
            additional_fields = log.get('additional_fields', {})
            
            # Parse workspace build events
            if resource_type == 'workspace_build':
                workspace_name = additional_fields.get('workspace_name', resource_target or 'workspace')
                
                if action == 'start':
                    # Workspace start indicates user session start
                    session_key = f"{user}:{workspace_name}"
                    user_sessions[session_key] = {
                        'start_time': time_str,
                        'ip': ip,
                        'workspace': workspace_name,
                        'user': user
                    }
                elif action in ['stop', 'delete']:
                    # Workspace stop indicates end of session
                    session_key = f"{user}:{workspace_name}"
                    if session_key in user_sessions:
                        session = user_sessions[session_key]
                        sessions.append({
                            'username': user,
                            'terminal': workspace_name[:24],
                            'ip': session.get('ip', ''),
                            'start_time': session['start_time'],
                            'end_time': time_str,
                            'duration': self.format_duration(session['start_time'], time_str)
                        })
                        del user_sessions[session_key]
        
        # Add ongoing sessions
        for session in user_sessions.values():
            sessions.append({
                'username': session['user'],
                'terminal': session['workspace'][:24],
                'ip': session.get('ip', ''),
                'start_time': session['start_time'],
                'end_time': None,
                'duration': 'still logged in'
            })
        
        # Sort by start time (most recent first)
        sessions.sort(key=lambda x: x['start_time'], reverse=True)
        
        return sessions[:limit]
    
    def format_time(self, time_str: str) -> str:
        """Format time like Unix last command"""
        try:
            dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            return dt.strftime('%a %b %d %H:%M')
        except:
            return time_str
    
    def print_sessions(self, sessions: List[Dict], show_hostnames: bool = True):
        """Print sessions in last command format"""
        if not sessions:
            print("No sessions found")
            return
        
        for session in sessions:
            username = session['username'][:8].ljust(8)  # Truncate/pad username
            terminal = session['terminal'][:24].ljust(24)  # Terminal/workspace name
            
            if show_hostnames and session['ip']:
                hostname = session['ip'][:16].ljust(16)
            else:
                hostname = " " * 16
            
            start_time = self.format_time(session['start_time'])
            
            if session['end_time']:
                end_time = self.format_time(session['end_time'])
                duration = session['duration']
                print(f"{username} {terminal} {hostname} {start_time} - {end_time} {duration}")
            else:
                print(f"{username} {terminal} {hostname} {start_time} {session['duration']}")
    
    def show_system_events(self, limit: int = 20):
        """Show system reboot/shutdown equivalent events"""
        # Look for template updates, system configuration changes
        query = "resource_type:template"
        logs = self.get_audit_logs(limit=limit, q=query)
        
        print("System events (template updates, configuration changes):")
        if not logs:
            print("No system events found")
            return
            
        for log in logs:
            time_str = self.format_time(log.get('time', ''))
            action = log.get('action', '')
            resource = log.get('resource_type', '')
            user = log.get('user', {}).get('username', 'system')
            resource_target = log.get('resource_target', '')
            print(f"system   {resource:<12} {time_str} ({action} {resource_target} by {user})")


def main():
    parser = argparse.ArgumentParser(
        description='Show Coder user session history (like Unix last command)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Show recent sessions
  %(prog)s -n 10                    # Show last 10 sessions  
  %(prog)s -u alice                 # Show sessions for user alice
  %(prog)s alice                    # Show sessions for user alice
  %(prog)s -R                       # Don't show IP addresses
  %(prog)s --system                 # Show system events
        """
    )
    
    parser.add_argument('username', nargs='?', help='Show sessions for specific user')
    parser.add_argument('-n', '--limit', type=int, default=20, 
                       help='Number of sessions to show (default: 20)')
    parser.add_argument('-R', '--no-hostname', action='store_true',
                       help='Suppress hostname/IP field')
    parser.add_argument('-u', '--user', help='Show sessions for specific user')
    parser.add_argument('--system', action='store_true',
                       help='Show system events (like reboot in last)')
    parser.add_argument('--url', default='http://localhost:7080',
                       help='Coder deployment URL (default: http://localhost:7080)')
    parser.add_argument('--token', help='Coder session token (or set CODER_SESSION_TOKEN)')
    
    args = parser.parse_args()
    
    # Get token from args or environment
    token = args.token or os.environ.get('CODER_SESSION_TOKEN')
    if not token:
        print("Error: Coder session token required. Use --token or set CODER_SESSION_TOKEN", 
              file=sys.stderr)
        sys.exit(1)
    
    coder_last = CoderLast(args.url, token)
    
    if args.system:
        coder_last.show_system_events(args.limit)
    else:
        username = args.user or args.username
        sessions = coder_last.get_user_sessions(username, args.limit)
        coder_last.print_sessions(sessions, not args.no_hostname)
        
        if sessions:
            # Show log file info like Unix last
            earliest_time = min(s['start_time'] for s in sessions if s['start_time'])
            earliest_formatted = coder_last.format_time(earliest_time)
            print(f"\naudit logs begin {earliest_formatted}")


if __name__ == '__main__':
    main()
