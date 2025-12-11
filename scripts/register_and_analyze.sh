#!/bin/bash

# Test script to analyze similarity between MCP servers from ToolHive
# Usage: ./scripts/register_and_analyze.sh

set -e

# Default to HTTPS since TLS is enabled by default (issue #51)
# Use -k flag to accept self-signed certificates
API_BASE="${API_BASE:-https://localhost:8000}"
CURL_OPTS="-k"  # Accept self-signed certificates
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BOLD}MCP Server Similarity Analysis${NC}\n"

echo -e "${YELLOW}Note: MCP server registration has been removed from the API.${NC}"
echo -e "${YELLOW}This script now analyzes similarity directly using server URLs.${NC}\n"

echo -e "${BOLD}Step 1: Fetching Running Servers from ToolHive${NC}\n"

# Check if thv is available
if ! command -v thv &> /dev/null; then
    echo -e "${RED}✗${NC} ToolHive (thv) command not found. Please install ToolHive first."
    exit 1
fi

# Get running servers from thv ls and parse them
echo "Fetching servers from ToolHive..."
thv_output=$(thv ls 2>/dev/null)

if [ -z "$thv_output" ]; then
    echo -e "${RED}✗${NC} No servers found or thv command failed"
    exit 1
fi

# Parse thv ls output to get server URLs
# Format: NAME PACKAGE STATUS URL ...
# Skip header line and extract URLs for running servers
SERVER_URLS=()
while read -r line; do
    # Skip empty lines
    [ -z "$line" ] && continue

    # Parse columns (space-separated)
    name=$(echo "$line" | awk '{print $1}')
    status=$(echo "$line" | awk '{print $3}')
    url=$(echo "$line" | awk '{print $4}')

    # Only use running servers
    if [ "$status" != "running" ]; then
        echo -e "${YELLOW}⊘${NC} Skipping $name (status: $status)"
        continue
    fi

    # Skip the toolhive-mcp-optimizer server
    if [ "$name" = "toolhive-mcp-optimizer" ]; then
        echo -e "${YELLOW}⊘${NC} Skipping $name (internal ToolHive server)"
        continue
    fi

    # Remove URL fragment (everything after #)
    clean_url=$(echo "$url" | sed 's/#.*//')

    echo -e "${GREEN}✓${NC} Found: $name ($clean_url)"
    SERVER_URLS+=("$clean_url")
done < <(echo "$thv_output" | tail -n +2)

if [ ${#SERVER_URLS[@]} -eq 0 ]; then
    echo -e "${RED}✗${NC} No running servers found"
    exit 1
fi

echo ""
echo -e "${GREEN}Total servers found:${NC} ${#SERVER_URLS[@]}"
echo ""

echo -e "${BOLD}Step 2: Running Similarity Analysis${NC}\n"

# If we have at least 2 servers, run comprehensive analysis
if [ ${#SERVER_URLS[@]} -ge 2 ]; then
    # Build JSON array of URLs
    URL_LIST_JSON=$(printf '%s\n' "${SERVER_URLS[@]}" | python3 -c "
import sys, json
urls = [line.strip() for line in sys.stdin if line.strip()]
print(json.dumps(urls))
")

    echo -e "${YELLOW}Analysis 1: All Detected Servers${NC}"
    echo "Comparing tools from ${#SERVER_URLS[@]} servers..."
    curl $CURL_OPTS -s -X POST "$API_BASE/similarity/analyze" \
        -H "Content-Type: application/json" \
        -d "{
            \"mcp_server_urls\": $URL_LIST_JSON,
            \"similarity_threshold\": 0.70,
            \"compute_full_similarity\": false
        }" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tool_count = len(data.get('tool_ids', []))
    print(f\"Tools analyzed: {tool_count}\")
    print(f\"Flagged pairs: {len(data.get('flagged_pairs', []))}\")

    if data.get('flagged_pairs'):
        print('\nHigh similarity pairs:')
        for pair in data['flagged_pairs'][:10]:
            print(f\"  • {pair['tool_a_id']} <-> {pair['tool_b_id']}: {pair['similarity_score']:.3f}\")
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.stdin.seek(0)
    print(sys.stdin.read())
"
    echo -e "\n"
fi

# If we have at least 2 servers, generate overlap matrix
if [ ${#SERVER_URLS[@]} -ge 2 ]; then
    echo -e "${YELLOW}Analysis 2: Overlap Matrix for All Servers${NC}"
    echo "Generating capability overlap matrix..."
    curl $CURL_OPTS -s -X POST "$API_BASE/similarity/overlap-matrix" \
        -H "Content-Type: application/json" \
        -d "{
            \"mcp_server_urls\": $URL_LIST_JSON,
            \"similarity_threshold\": 0.70
        }" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tool_ids = data.get('tool_ids', [])
    print(f\"Tools in matrix: {len(tool_ids)}\")
    print(f\"Dimensions analyzed: {', '.join(data.get('dimensions', {}).keys())}\")

    # Show a few high-overlap pairs
    matrix = data.get('matrix', [])

    if matrix and tool_ids:
        print('\nTop overlapping pairs:')
        overlaps = []
        for i in range(len(matrix)):
            for j in range(i+1, len(matrix)):
                if len(matrix[i]) > j and matrix[i][j] > 0.6:
                    overlaps.append((tool_ids[i], tool_ids[j], matrix[i][j]))

        overlaps.sort(key=lambda x: x[2], reverse=True)
        for tool_a, tool_b, score in overlaps[:10]:
            print(f\"  • {tool_a} <-> {tool_b}: {score:.3f}\")
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.stdin.seek(0)
    print(sys.stdin.read())
"
    echo -e "\n"
fi

echo -e "${BOLD}${GREEN}✓ Analysis Complete!${NC}\n"

echo -e "${BOLD}Next Steps:${NC}"
echo "  • View detailed results in the API response"
echo "  • Try analyzing specific server combinations"
echo "  • Adjust similarity_threshold to see more/fewer matches"
echo "  • Use /similarity/recommendations for specific tool pairs"
echo
echo -e "Example commands:"
echo -e "  ${BLUE}# Get tools from a specific server${NC}"
echo "  curl $CURL_OPTS -s \"$API_BASE/mcp-servers/tools?server_url=http://localhost:3000\" | python3 -m json.tool"
echo
echo -e "  ${BLUE}# Compare specific servers by URL${NC}"
echo "  curl $CURL_OPTS -X POST \"$API_BASE/similarity/analyze\" \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"url_list\": [\"http://localhost:3000\", \"http://localhost:3001\"], \"similarity_threshold\": 0.70}'"

