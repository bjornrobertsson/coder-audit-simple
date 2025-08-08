#!/bin/bash

# Coder Workspace TTL and Dormancy Manager - BASH/curl version
# Converted from get_and_bump_ttl_workspaces.py with dormancy extension capabilities

# Configuration
CODER_URL="${CODER_URL:-https://coder.example.com}"
CODER_TOKEN="${CODER_TOKEN}"
DEFAULT_TTL_HOURS="${DEFAULT_TTL_HOURS:-8}"
DRY_RUN="${DRY_RUN:-false}"
PLUS_ONE_WORKSPACE_TTL="${PLUS_ONE_WORKSPACE_TTL:-false}"
PLUS_ONE_DORMANCY_TTL="${PLUS_ONE_DORMANCY_TTL:-false}"
DORMANCY_EXTENSION_HOURS="${DORMANCY_EXTENSION_HOURS:-24}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Function to print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check if required tools are available
check_dependencies() {
    for cmd in curl jq bc date; do
        if ! command -v $cmd &> /dev/null; then
            print_color "$RED" "Error: $cmd is required but not installed."
            exit 1
        fi
    done
}

# Function to check authentication
check_auth() {
    if [[ -z "$CODER_TOKEN" ]]; then
        print_color "$RED" "Error: CODER_TOKEN environment variable is required"
        print_color "$YELLOW" "Generate a token at: $CODER_URL/settings/tokens"
        exit 1
    fi
}

# Function to make authenticated API requests
api_request() {
    local method=$1
    local endpoint=$2
    local data=${3:-}
    
    local url="$CODER_URL/api/v2$endpoint"
    
    if [[ -n "$data" ]]; then
        curl -s -X "$method" \
            -H "Content-Type: application/json" \
            -H "Coder-Session-Token: $CODER_TOKEN" \
            -d "$data" \
            "$url"
    else
        curl -s -X "$method" \
            -H "Coder-Session-Token: $CODER_TOKEN" \
            "$url"
    fi
}

# Function to get all workspaces
get_workspaces() {
    local query=${1:-}
    local endpoint="/workspaces"
    
    if [[ -n "$query" ]]; then
        endpoint="$endpoint?q=$query"
    fi
    
    api_request "GET" "$endpoint"
}

# Function to get workspace by ID
get_workspace() {
    local workspace_id=$1
    api_request "GET" "/workspaces/$workspace_id"
}

# Function to update workspace TTL
update_workspace_ttl() {
    local workspace_id=$1
    local ttl_ms=$2
    
    local data="{\"ttl_ms\": $ttl_ms}"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_color "$YELLOW" "DRY RUN: Would update workspace $workspace_id with TTL: ${ttl_ms}ms"
        return 0
    fi
    
    api_request "PUT" "/workspaces/$workspace_id/ttl" "$data"
}

# Function to extend workspace TTL (for running workspaces)
extend_workspace_ttl() {
    local workspace_id=$1
    local extension_ms=$2
    
   #  local data="{\"deadline\": \"$(date -d "+$((extension_ms / 1000 / 3600)) hours\" -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    local data="{\"deadline\": \"$(date -d \"+$((extension_ms / 1000 / 3600)) hours\" -u +%Y-%m-%dT%H:%M:%SZ)\"}"

    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_color "$YELLOW" "DRY RUN: Would extend workspace $workspace_id by: ${extension_ms}ms"
        return 0
    fi
    
    api_request "PUT" "/workspaces/$workspace_id/extend" "$data"
}

# Function to manage workspace dormancy
manage_workspace_dormancy() {
    local workspace_id=$1
    local set_dormant=$2  # true or false
    
    local data="{\"dormant\": $set_dormant}"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_color "$YELLOW" "DRY RUN: Would set dormancy for workspace $workspace_id to: $set_dormant"
        return 0
    fi
    
    api_request "PUT" "/workspaces/$workspace_id/dormant" "$data"
}

# Function to extend dormant workspace deletion time
extend_dormant_workspace() {
    local workspace_id=$1
    local extension_hours=$2
    
    print_color "$CYAN" "Extending dormant workspace $workspace_id by $extension_hours hours..."
    
    # First, get the current workspace details
    local workspace_data
    workspace_data=$(get_workspace "$workspace_id")
    
    if [[ $? -ne 0 ]]; then
        print_color "$RED" "Failed to get workspace details for $workspace_id"
        return 1
    fi
    
    local current_deleting_at
    current_deleting_at=$(echo "$workspace_data" | jq -r '.deleting_at // empty')
    
    if [[ -z "$current_deleting_at" || "$current_deleting_at" == "null" ]]; then
        print_color "$YELLOW" "Workspace $workspace_id is not scheduled for deletion"
        return 1
    fi
    
    # Calculate new deletion time
    local current_timestamp
    current_timestamp=$(date -d "$current_deleting_at" +%s)
    local extension_seconds=$((extension_hours * 3600))
    local new_timestamp=$((current_timestamp + extension_seconds))
    local new_deleting_at
    new_deleting_at=$(date -d "@$new_timestamp" -u +%Y-%m-%dT%H:%M:%SZ)
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_color "$YELLOW" "DRY RUN: Would extend deletion time for workspace $workspace_id"
        print_color "$YELLOW" "  Current deletion time: $current_deleting_at"
        print_color "$YELLOW" "  New deletion time: $new_deleting_at"
        return 0
    fi
    
    # Un-dormant the workspace temporarily to reset the deletion timer
    print_color "$CYAN" "Temporarily un-dormanting workspace to reset deletion timer..."
    local undormant_result
    undormant_result=$(manage_workspace_dormancy "$workspace_id" "false")
    
    if [[ $? -ne 0 ]]; then
        print_color "$RED" "Failed to un-dormant workspace $workspace_id"
        return 1
    fi
    
    # Wait a moment for the change to propagate
    sleep 2
    
    # Re-dormant the workspace with extended time
    print_color "$CYAN" "Re-dormanting workspace with extended deletion time..."
    local redormant_result
    redormant_result=$(manage_workspace_dormancy "$workspace_id" "true")
    
    if [[ $? -eq 0 ]]; then
        print_color "$GREEN" "‚úì Successfully extended dormant workspace deletion time by $extension_hours hours"
        return 0
    else
        print_color "$RED" "‚úó Failed to re-dormant workspace $workspace_id"
        return 1
    fi
}

# Function to convert hours to milliseconds
hours_to_ms() {
    local hours=$1
    echo $((hours * 60 * 60 * 1000))
}

# Function to convert milliseconds to hours
ms_to_hours() {
    local ms=$1
    if [[ "$ms" == "0" || "$ms" == "null" ]]; then
        echo "‚àû"
    else
        echo "scale=1; $ms / (60 * 60 * 1000)" | bc -l
    fi
}

# Function to format date/time for display
format_datetime() {
    local date_str=$1
    if [[ "$date_str" == "null" || -z "$date_str" ]]; then
        echo "Never"
    else
        # Convert ISO date to readable format
        date -d "$date_str" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "$date_str"
    fi
}

# Function to calculate time remaining until deletion
calculate_time_remaining() {
    local deletion_time=$1
    if [[ "$deletion_time" == "null" || -z "$deletion_time" ]]; then
        echo "N/A"
        return
    fi
    
    local deletion_timestamp
    deletion_timestamp=$(date -d "$deletion_time" +%s 2>/dev/null)
    local current_timestamp
    current_timestamp=$(date +%s)
    
    if [[ $? -ne 0 ]]; then
        echo "N/A"
        return
    fi
    
    local remaining_seconds=$((deletion_timestamp - current_timestamp))
    
    if [[ $remaining_seconds -le 0 ]]; then
        echo "Overdue"
    else
        local days=$((remaining_seconds / 86400))
        local hours=$(((remaining_seconds % 86400) / 3600))
        local minutes=$(((remaining_seconds % 3600) / 60))
        
        if [[ $days -gt 0 ]]; then
            echo "${days}d ${hours}h ${minutes}m"
        elif [[ $hours -gt 0 ]]; then
            echo "${hours}h ${minutes}m"
        else
            echo "${minutes}m"
        fi
    fi
}

# Function to process workspaces and manage TTL/dormancy
process_workspaces() {
    local filter_query=${1:-""}
    local action=${2:-"bump_ttl"}  # bump_ttl, extend_dormancy, list
    
    print_color "$BLUE" "Fetching workspaces..."
    
    # Get workspaces with optional filter
    local workspaces_json
    workspaces_json=$(get_workspaces "$filter_query")
    
    if [[ $? -ne 0 ]]; then
        print_color "$RED" "Failed to fetch workspaces"
        exit 1
    fi
    
    # Parse workspace count
    local workspace_count
    workspace_count=$(echo "$workspaces_json" | jq -r '.count // 0')
    
    print_color "$GREEN" "Found $workspace_count workspaces"
    
    if [[ "$workspace_count" == "0" ]]; then
        print_color "$YELLOW" "No workspaces found matching criteria"
        return 0
    fi
    
    # Default TTL in milliseconds
    local default_ttl_ms
    default_ttl_ms=$(hours_to_ms "$DEFAULT_TTL_HOURS")
    
    # Display header based on action
    case "$action" in
        "extend_dormancy")
            echo -e "\n| Workspace Name | Owner | Status | Dormant | Delete In | Action |"
            echo "|----------------|-------|---------|---------|-----------|--------|"
            ;;
        *)
            echo -e "\n| Workspace Name | Owner | Status | Current TTL | Last Used | Dormant | Action |"
            echo "|----------------|-------|---------|-------------|-----------|---------|--------|"
            ;;
    esac
    
    # Process each workspace
    echo "$workspaces_json" | jq -r '.workspaces[] | @base64' | while read -r workspace; do
        local ws_data
        ws_data=$(echo "$workspace" | base64 --decode)
        
        local ws_id=$(echo "$ws_data" | jq -r '.id')
        local ws_name=$(echo "$ws_data" | jq -r '.name')
        local ws_owner=$(echo "$ws_data" | jq -r '.owner_name // "unknown"')
        local ws_status=$(echo "$ws_data" | jq -r '.latest_build.status // "unknown"')
        local ws_ttl_ms=$(echo "$ws_data" | jq -r '.ttl_ms // 0')
        local ws_last_used=$(echo "$ws_data" | jq -r '.last_used_at')
        local ws_dormant_at=$(echo "$ws_data" | jq -r '.dormant_at')
        local ws_deleting_at=$(echo "$ws_data" | jq -r '.deleting_at')
        
        # Format values for display
        local current_ttl_display
        current_ttl_display=$(ms_to_hours "$ws_ttl_ms")
        
        local last_used_display
        last_used_display=$(format_datetime "$ws_last_used")
        
        local dormant_display="No"
        if [[ "$ws_dormant_at" != "null" && -n "$ws_dormant_at" ]]; then
            dormant_display="Yes"
        fi
        
        local delete_in_display
        delete_in_display=$(calculate_time_remaining "$ws_deleting_at")
        
        local action_taken="No action needed"
        local needs_action=false
        
        case "$action" in
            "extend_dormancy")
                # Only process dormant workspaces
                if [[ "$dormant_display" == "Yes" ]]; then
                    action_taken="Extend deletion by ${DORMANCY_EXTENSION_HOURS}h"
                    needs_action=true
                fi
                
                printf "| %-14s | %-5s | %-7s | %-7s | %-9s | %-6s |\n" \
                    "$ws_name" "$ws_owner" "$ws_status" "$dormant_display" \
                    "$delete_in_display" "$action_taken"
                
                if [[ "$needs_action" == "true" ]]; then
                    extend_dormant_workspace "$ws_id" "$DORMANCY_EXTENSION_HOURS"
                fi
                ;;
            
            "bump_ttl"|*)
                # Check if workspace needs TTL update
                if [[ "$ws_ttl_ms" == "0" || "$ws_ttl_ms" == "null" ]]; then
                    action_taken="Set TTL to ${DEFAULT_TTL_HOURS}h"
                    needs_action=true
                elif [[ "$ws_ttl_ms" -lt "$default_ttl_ms" ]]; then
                    action_taken="Bump TTL to ${DEFAULT_TTL_HOURS}h"
                    needs_action=true
                fi
                
                # Apply PlusOne logic for workspace TTL
                if [[ "$PLUS_ONE_WORKSPACE_TTL" == "true" && "$needs_action" == "true" ]]; then
                    local plus_one_ttl_ms
                    plus_one_ttl_ms=$(hours_to_ms $((DEFAULT_TTL_HOURS + 1)))
                    action_taken="PlusOne TTL to $((DEFAULT_TTL_HOURS + 1))h"
                    default_ttl_ms="$plus_one_ttl_ms"
                fi
                
                printf "| %-14s | %-5s | %-7s | %-11s | %-9s | %-7s | %-6s |\n" \
                    "$ws_name" "$ws_owner" "$ws_status" "${current_ttl_display}h" \
                    "$last_used_display" "$dormant_display" "$action_taken"
                
                # Update TTL if needed
                if [[ "$needs_action" == "true" ]]; then
                    local result
                    if [[ "$ws_status" == "running" ]]; then
                        # For running workspaces, use extend endpoint
                        result=$(extend_workspace_ttl "$ws_id" "$default_ttl_ms")
                    else
                        # For stopped workspaces, use TTL endpoint
                        result=$(update_workspace_ttl "$ws_id" "$default_ttl_ms")
                    fi
                    
                    if [[ $? -eq 0 ]]; then
                        if [[ "$DRY_RUN" != "true" ]]; then
                            print_color "$GREEN" "‚úì Successfully updated TTL for workspace: $ws_name"
                        fi
                    else
                        print_color "$RED" "‚úó Failed to update TTL for workspace: $ws_name"
                        echo "Error: $result"
                    fi
                fi
                ;;
        esac
    done
}

# Function to set template dormancy settings
set_template_dormancy() {
    local template_id=$1
    local dormancy_threshold_hours=${2:-0}    # Hours before marking dormant (0 = disabled)
    local dormancy_deletion_hours=${3:-0}     # Hours dormant before deletion (0 = disabled)
    
    # Convert hours to milliseconds
    local threshold_ms=$((dormancy_threshold_hours * 60 * 60 * 1000))
    local deletion_ms=$((dormancy_deletion_hours * 60 * 60 * 1000))
    
    # Apply PlusOne logic for dormancy TTL
    local actual_deletion_hours=$dormancy_deletion_hours
    if [[ "$PLUS_ONE_DORMANCY_TTL" == "true" && "$dormancy_deletion_hours" -gt 0 ]]; then
        actual_deletion_hours=$((dormancy_deletion_hours + 1))
        deletion_ms=$((actual_deletion_hours * 60 * 60 * 1000))
        print_color "$CYAN" "Applying PlusOne to dormancy deletion: ${actual_deletion_hours} hours"
    fi
    
    # Prepare the JSON payload for PATCH request
    local payload=$(cat << EOF
{
    "dormancy_threshold_ms": $threshold_ms,
    "dormancy_auto_deletion_ms": $deletion_ms
}
EOF
)
    
    print_color "$BLUE" "Setting dormancy settings for template $template_id:"
    print_color "$BLUE" "  - Dormancy threshold: ${dormancy_threshold_hours} hours"
    if [[ "$PLUS_ONE_DORMANCY_TTL" == "true" && "$dormancy_deletion_hours" -gt 0 ]]; then
        print_color "$BLUE" "  - Auto-deletion after: ${actual_deletion_hours} hours - PlusOne applied"
    else
        print_color "$BLUE" "  - Auto-deletion after: ${dormancy_deletion_hours} hours"
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_color "$YELLOW" "DRY RUN: Would update template dormancy settings"
        print_color "$YELLOW" "Payload: $payload"
        return 0
    fi
    
    # Make the PATCH request to update template settings
    local response
    response=$(curl -s -w "%{http_code}" \
        -X PATCH \
        -H "Content-Type: application/json" \
        -H "Coder-Session-Token: $CODER_TOKEN" \
        -d "$payload" \
        "$CODER_URL/api/v2/templates/$template_id")
    
    local http_code="${response: -3}"
    local response_body="${response%???}"
    
    if [[ "$http_code" == "200" ]]; then
        print_color "$GREEN" "‚úì Successfully updated dormancy settings"
        return 0
    else
        print_color "$RED" "‚úó Failed to update dormancy settings - HTTP - $http_code"
        echo "Response: $response_body"
        return 1
    fi
}

# Function to get template information including current dormancy settings
get_template_dormancy() {
    local template_id=$1
    
    local response
    response=$(api_request "GET" "/templates/$template_id")
    
    if [[ $? -eq 0 ]]; then
        print_color "$BLUE" "Current dormancy settings:"
        echo "$response" | jq -r '
            "Template: " + .name,
            "Dormancy Threshold: " + (if .dormancy_threshold_ms and .dormancy_threshold_ms > 0 then (.dormancy_threshold_ms / (60*60*1000) | tostring) + " hours" else "disabled" end),
            "Auto-deletion: " + (if .dormancy_auto_deletion_ms and .dormancy_auto_deletion_ms > 0 then (.dormancy_auto_deletion_ms / (60*60*1000) | tostring) + " hours" else "disabled" end)
        '
    else
        print_color "$RED" "Failed to fetch template information"
        return 1
    fi
}

# Function to list all templates with their dormancy settings
list_template_dormancy() {
    print_color "$BLUE" "Fetching all templates with dormancy settings..."
    
    local response
    response=$(api_request "GET" "/templates")
    
    echo -e "\n| Template Name | Dormancy Threshold | Auto-Deletion |"
    echo "|---------------|-------------------|----------------|"
    
    echo "$response" | jq -r '.templates[]? // .[]? // empty | @base64' | while read -r template; do
        if [[ -z "$template" ]]; then
            continue
        fi
        
        local template_data
        template_data=$(echo "$template" | base64 --decode 2>/dev/null)
        
        if [[ $? -ne 0 ]]; then
            continue
        fi
        
        local name=$(echo "$template_data" | jq -r '.name // "unknown"')
        local threshold_ms=$(echo "$template_data" | jq -r '.dormancy_threshold_ms // 0')
        local deletion_ms=$(echo "$template_data" | jq -r '.dormancy_auto_deletion_ms // 0')
        
        local threshold_hours="disabled"
        local deletion_hours="disabled"
        
        if [[ "$threshold_ms" != "0" && "$threshold_ms" != "null" && "$threshold_ms" -gt 0 ]]; then
            threshold_hours="$(echo "scale=1; $threshold_ms / (60 * 60 * 1000)" | bc -l)h"
        fi
        
        if [[ "$deletion_ms" != "0" && "$deletion_ms" != "null" && "$deletion_ms" -gt 0 ]]; then
            deletion_hours="$(echo "scale=1; $deletion_ms / (60 * 60 * 1000)" | bc -l)h"
        fi
        
        printf "| %-13s | %-17s | %-14s |\n" \
            "$name" "$threshold_hours" "$deletion_hours"
    done
}

# Function to display help
show_help() {
    cat << EOF
Coder Workspace TTL and Dormancy Manager - BASH/curl version

USAGE:
    $0 [OPTIONS] [FILTER]

OPTIONS:
    -h, --help                  Show this help message
    -d, --dry-run              Show what would be changed without making changes
    -t, --ttl HOURS            Set default TTL in hours (default: 8)
    -u, --url URL              Coder instance URL (default: from CODER_URL env var)
    --plus-one-workspace-ttl   Add one extra hour to workspace TTL updates
    --plus-one-dormancy-ttl    Add one extra hour to dormancy deletion settings
    --extend-dormancy          Extend deletion time for dormant workspaces
    --dormancy-extension HOURS Hours to extend dormant workspaces (default: 24)
    
    Template Dormancy Commands:
    --template-dormancy TEMPLATE_ID THRESHOLD_HOURS DELETION_HOURS
                              Set dormancy settings for a template
    --get-template-dormancy TEMPLATE_ID
                              Get current dormancy settings for a template
    --list-template-dormancy  List all templates with dormancy settings

FILTER:
    Optional query filter for workspaces (e.g., "owner:me", "status:running", "dormant:true")

EXAMPLES:
    # Update TTL for all workspaces
    $0

    # Dry run to see what would change
    $0 --dry-run

    # Update only running workspaces with PlusOne hour
    $0 --plus-one-workspace-ttl "status:running"

    # Extend dormant workspaces by 48 hours
    $0 --extend-dormancy --dormancy-extension 48 "dormant:true"

    # Update workspaces owned by current user
    $0 "owner:me"

    # Set custom TTL of 12 hours with PlusOne (results in 13 hours)
    $0 --ttl 12 --plus-one-workspace-ttl

    # Set template dormancy: 30 days inactive -> dormant, 7 days dormant -> delete
    $0 --template-dormancy "template-id-here" 720 168

    # Set template dormancy with PlusOne (8 days dormant -> delete)  
    $0 --template-dormancy "template-id-here" 720 168 --plus-one-dormancy-ttl

    # Get dormancy settings for a template
    $0 --get-template-dormancy "template-id-here"

    # List all templates with their dormancy settings
    $0 --list-template-dormancy

ENVIRONMENT VARIABLES:
    CODER_URL                   Coder instance URL (required)
    CODER_TOKEN                 Coder session token (required)
    DEFAULT_TTL_HOURS           Default TTL in hours (optional, default: 8)
    DRY_RUN                     Set to 'true' for dry run mode (optional)
    PLUS_ONE_WORKSPACE_TTL      Set to 'true' to add one hour to workspace TTL
    PLUS_ONE_DORMANCY_TTL       Set to 'true' to add one hour to dormancy deletion
    DORMANCY_EXTENSION_HOURS    Hours to extend dormant workspaces (optional, default: 24)

DORMANCY FEATURES:
    This script supports Coder's Premium dormancy features:
    - Extending deletion time for dormant workspaces
    - Configuring template-level dormancy thresholds
    - PlusOne functionality to add extra time buffers
    - Comprehensive dormancy status reporting

EOF
}

# Main function
main() {
    local filter_query=""
    local action="bump_ttl"
    local template_id=""
    local threshold_hours=""
    local deletion_hours=""
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -d|--dry-run)
                DRY_RUN="true"
                shift
                ;;
            -t|--ttl)
                DEFAULT_TTL_HOURS="$2"
                shift 2
                ;;
            -u|--url)
                CODER_URL="$2"
                shift 2
                ;;
            --plus-one-workspace-ttl)
                PLUS_ONE_WORKSPACE_TTL="true"
                shift
                ;;
            --plus-one-dormancy-ttl)
                PLUS_ONE_DORMANCY_TTL="true"
                shift
                ;;
            --extend-dormancy)
                action="extend_dormancy"
                shift
                ;;
            --dormancy-extension)
                DORMANCY_EXTENSION_HOURS="$2"
                shift 2
                ;;
            --template-dormancy)
                action="template_dormancy"
                template_id="$2"
                threshold_hours="$3"
                deletion_hours="$4"
                shift 4
                ;;
            --get-template-dormancy)
                action="get_template_dormancy"
                template_id="$2"
                shift 2
                ;;
            --list-template-dormancy)
                action="list_template_dormancy"
                shift
                ;;
            -*)
                print_color "$RED" "Unknown option: $1"
                show_help
                exit 1
                ;;
            *)
                filter_query="$1"
                shift
                ;;
        esac
    done
    
    # Check dependencies and authentication
    check_dependencies
    check_auth
    
    # Display configuration
    print_color "$BLUE" "Coder Workspace TTL and Dormancy Manager"
    print_color "$BLUE" "========================================"
    echo "Coder URL: $CODER_URL"
    echo "Default TTL: ${DEFAULT_TTL_HOURS} hours"
    echo "Dry Run: $DRY_RUN"
    echo "PlusOne Workspace TTL: $PLUS_ONE_WORKSPACE_TTL"
    echo "PlusOne Dormancy TTL: $PLUS_ONE_DORMANCY_TTL"
    echo "Dormancy Extension: ${DORMANCY_EXTENSION_HOURS} hours"
    
    if [[ -n "$filter_query" ]]; then
        echo "Filter: $filter_query"
    fi
    echo ""
    
    # Execute based on action
    case "$action" in
        "template_dormancy")
            if [[ -z "$template_id" || -z "$threshold_hours" || -z "$deletion_hours" ]]; then
                print_color "$RED" "Error: Template ID, threshold hours, and deletion hours are required"
                show_help
                exit 1
            fi
            set_template_dormancy "$template_id" "$threshold_hours" "$deletion_hours"
            ;;
        "get_template_dormancy")
            if [[ -z "$template_id" ]]; then
                print_color "$RED" "Error: Template ID is required"
                show_help
                exit 1
            fi
            get_template_dormancy "$template_id"
            ;;
        "list_template_dormancy")
            list_template_dormancy
            ;;
        *)
            # Process workspaces (bump_ttl or extend_dormancy)
            process_workspaces "$filter_query" "$action"
            ;;
    esac
}

# Run main function with all arguments
main "$@"
