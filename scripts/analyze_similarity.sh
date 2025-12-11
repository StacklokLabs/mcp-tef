#!/usr/bin/env bash
#
# analyze_similarity.sh - Run similarity analysis between MCP server tools
#
# Usage:
#   ./scripts/analyze_similarity.sh http://localhost:3000 http://localhost:3001
#   ./scripts/analyze_similarity.sh --threshold 0.75 http://localhost:3000 http://localhost:3001
#   ./scripts/analyze_similarity.sh --recommendations http://localhost:3000 http://localhost:3001
#   ./scripts/analyze_similarity.sh --help
#

set -euo pipefail

# Default values
API_URL="${MCP_TEF_API_URL:-https://localhost:8000}"
THRESHOLD=0.9
INCLUDE_RECOMMENDATIONS=false
OUTPUT_FORMAT="json"  # json or summary

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Help text
show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] SERVER_URL1 SERVER_URL2 [SERVER_URL3...]

Run similarity analysis between tools from multiple MCP servers.

OPTIONS:
    -t, --threshold FLOAT       Similarity threshold (0.0-1.0, default: 0.9)
    -r, --recommendations       Include AI-powered differentiation recommendations
    -s, --summary              Show summary instead of full JSON output
    -u, --url URL              API base URL (default: https://localhost:8000)
    -h, --help                 Show this help message
    -a, --auto                 Auto-detect servers using 'thv ls'

EXAMPLES:
    # Auto-detect all servers from 'thv ls'
    $(basename "$0") --auto

    # Specific server URLs
    $(basename "$0") http://localhost:3000 http://localhost:3001

    # Lower threshold to find more pairs
    $(basename "$0") --threshold 0.5 http://localhost:3000 http://localhost:3001

    # With AI recommendations
    $(basename "$0") --recommendations http://localhost:3000 http://localhost:3001

    # Show summary of results
    $(basename "$0") --summary http://localhost:3000 http://localhost:3001 http://localhost:3002

    # Analyze multiple servers
    $(basename "$0") http://localhost:3000 http://localhost:3001 http://localhost:3002

ENVIRONMENT VARIABLES:
    MCP_TEF_API_URL           Override default API URL

NOTES:
    - Server URLs must be accessible (MCP servers must be running)
    - The API loads tools directly from server URLs (no pre-registration needed)
    - Minimum 2 server URLs required for similarity analysis
EOF
}

# Parse command line arguments
SERVER_URLS=()
AUTO_DETECT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -t|--threshold)
            THRESHOLD="$2"
            shift 2
            ;;
        -r|--recommendations)
            INCLUDE_RECOMMENDATIONS=true
            shift
            ;;
        -s|--summary)
            OUTPUT_FORMAT="summary"
            shift
            ;;
        -u|--url)
            API_URL="$2"
            shift 2
            ;;
        -a|--auto)
            AUTO_DETECT=true
            shift
            ;;
        -*)
            echo -e "${RED}Error: Unknown option $1${NC}" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
        *)
            SERVER_URLS+=("$1")
            shift
            ;;
    esac
done

# Auto-detect servers if none provided
if [[ ${#SERVER_URLS[@]} -eq 0 ]] && [[ "$AUTO_DETECT" == "true" ]]; then
    if command -v thv &> /dev/null; then
        echo -e "${BLUE}Auto-detecting servers from 'thv ls'...${NC}"

        # Get server URLs from thv ls
        THV_OUTPUT=$(thv ls 2>&1)

        if [[ $? -ne 0 ]]; then
            echo -e "${RED}Error: 'thv ls' command failed${NC}" >&2
            echo "$THV_OUTPUT" >&2
            echo ""
            echo "Please specify server URLs manually:" >&2
            echo "  $(basename "$0") http://localhost:3000 http://localhost:3001 ..." >&2
            exit 1
        fi

        # Parse server URLs from thv ls output
        # Format: NAME PACKAGE STATUS URL ...
        # Skip header lines, empty lines, and extract URLs (column 4)
        mapfile -t SERVER_URLS < <(
            echo "$THV_OUTPUT" | \
            tail -n +2 | \
            grep -v '^$' | \
            awk '$3 == "running" && $1 != "toolhive-mcp-optimizer" {print $4}' | \
            sed 's/#.*//' | \
            grep -v '^$'
        )

        if [[ ${#SERVER_URLS[@]} -eq 0 ]]; then
            echo -e "${RED}Error: No running servers found from 'thv ls'${NC}" >&2
            echo "Command output:" >&2
            echo "$THV_OUTPUT" >&2
            echo ""
            echo "Please specify server URLs manually" >&2
            exit 1
        fi

        echo -e "${GREEN}Found ${#SERVER_URLS[@]} running servers:${NC}"
        for url in "${SERVER_URLS[@]}"; do
            echo -e "  ${BLUE}${url}${NC}"
        done
    else
        echo -e "${RED}Error: No server URLs provided and 'thv' command not found${NC}" >&2
        echo "Please either:" >&2
        echo "  1. Provide server URLs: $(basename "$0") http://localhost:3000 http://localhost:3001 ..." >&2
        echo "  2. Install 'thv' command and use --auto flag for auto-detection" >&2
        exit 1
    fi
elif [[ ${#SERVER_URLS[@]} -eq 0 ]]; then
    echo -e "${RED}Error: No server URLs provided${NC}" >&2
    echo "Usage: $(basename "$0") [OPTIONS] SERVER_URL1 SERVER_URL2 ..." >&2
    echo "Use --help for more information or --auto for auto-detection" >&2
    exit 1
fi

# Validate inputs
if [[ ${#SERVER_URLS[@]} -lt 2 ]]; then
    echo -e "${RED}Error: At least 2 server URLs required${NC}" >&2
    echo "Usage: $(basename "$0") [OPTIONS] SERVER_URL1 SERVER_URL2 [SERVER_URL3...]" >&2
    echo "Use --help for more information" >&2
    exit 1
fi

# Build JSON array of server URLs
SERVER_URLS_JSON=$(printf '%s\n' "${SERVER_URLS[@]}" | jq -R . | jq -s .)

# Build request payload
REQUEST_PAYLOAD=$(jq -n \
    --argjson mcp_server_urls "$SERVER_URLS_JSON" \
    --argjson threshold "$THRESHOLD" \
    --argjson include_recommendations "$INCLUDE_RECOMMENDATIONS" \
    '{
        mcp_server_urls: $mcp_server_urls,
        similarity_threshold: $threshold,
        include_recommendations: $include_recommendations
    }')

echo -e "${BLUE}Analyzing similarity between servers:${NC}"
for url in "${SERVER_URLS[@]}"; do
    echo -e "  ${BLUE}${url}${NC}"
done
echo -e "${BLUE}Threshold:${NC} $THRESHOLD"
echo -e "${BLUE}Recommendations:${NC} $INCLUDE_RECOMMENDATIONS"
echo ""

# Make API request
RESPONSE=$(curl -s -k -X POST "${API_URL}/similarity/analyze" \
    -H "Content-Type: application/json" \
    -d "$REQUEST_PAYLOAD")

# Check for errors
if echo "$RESPONSE" | jq -e '.error' > /dev/null 2>&1; then
    echo -e "${RED}Error:${NC} $(echo "$RESPONSE" | jq -r '.message')" >&2
    exit 1
fi

# Output results
if [[ "$OUTPUT_FORMAT" == "summary" ]]; then
    # Extract summary statistics
    TOOL_COUNT=$(echo "$RESPONSE" | jq -r '.tool_ids | length')
    FLAGGED_COUNT=$(echo "$RESPONSE" | jq -r '.flagged_pairs | length')
    TOTAL_PAIRS=$(( TOOL_COUNT * (TOOL_COUNT - 1) / 2 ))
    
    echo -e "${GREEN}=== Similarity Analysis Summary ===${NC}"
    echo ""
    echo -e "${BLUE}Total tools analyzed:${NC} $TOOL_COUNT"
    echo -e "${BLUE}Total tool pairs:${NC} $TOTAL_PAIRS"
    echo -e "${BLUE}Pairs above threshold:${NC} $FLAGGED_COUNT"
    
    if [[ $FLAGGED_COUNT -gt 0 ]]; then
        echo ""
        echo -e "${YELLOW}Top 10 Most Similar Pairs:${NC}"
        echo "$RESPONSE" | jq -r '
            .flagged_pairs 
            | sort_by(-.similarity_score) 
            | limit(10; .[])
            | "  \(.tool_a_id) ↔ \(.tool_b_id): \(.similarity_score * 100 | round / 100)"
        '
        
        # Show distribution
        echo ""
        echo -e "${YELLOW}Similarity Distribution:${NC}"
        echo "$RESPONSE" | jq -r '
            def score_bucket:
                if . >= 0.9 then "0.9-1.0"
                elif . >= 0.8 then "0.8-0.9"
                elif . >= 0.7 then "0.7-0.8"
                elif . >= 0.6 then "0.6-0.7"
                elif . >= 0.5 then "0.5-0.6"
                else "0.0-0.5" end;
            
            .flagged_pairs 
            | group_by(.similarity_score | score_bucket)
            | map({range: .[0].similarity_score | score_bucket, count: length})
            | sort_by(.range)
            | reverse
            | .[]
            | "  \(.range): \(.count) pairs"
        '
        
        if [[ "$INCLUDE_RECOMMENDATIONS" == "true" ]]; then
            RECS_COUNT=$(echo "$RESPONSE" | jq -r '.recommendations | length')
            echo ""
            echo -e "${GREEN}Generated $RECS_COUNT recommendations${NC}"
            echo "Use full JSON output to view recommendations"
        fi
    else
        echo ""
        echo -e "${GREEN}No tool pairs found above threshold $THRESHOLD${NC}"
        echo "Try lowering the threshold with --threshold"
    fi
    
    echo ""
    echo -e "${BLUE}Full results saved to:${NC} similarity_results.json"
    echo "$RESPONSE" | jq '.' > similarity_results.json
    
else
    # Full JSON output
    echo "$RESPONSE" | jq '.'
fi

