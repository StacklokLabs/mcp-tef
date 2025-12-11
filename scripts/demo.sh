#!/bin/bash

# ============================================================================
# MCP TEF API Demo Script
# ============================================================================
# 
# This script demonstrates all API endpoints with detailed explanations
# for the UI team to understand the API structure and functionality.
#
# Usage: ./scripts/demo.sh
#
# Prerequisites:
# - API server running on https://localhost:8000 (or set BASE_URL)
# - jq installed for JSON formatting (optional but recommended)
# - thv (ToolHive) installed for auto-detecting running MCP servers (optional)
# - At least 2 running MCP servers for similarity analysis examples (optional)
#   Without running servers, similarity examples will be skipped with informative messages
# ============================================================================

set -e

# Configuration
# Default to HTTPS since TLS is enabled by default (issue #51)
# Use -k flag to accept self-signed certificates
BASE_URL="${BASE_URL:-https://localhost:8000}"
DATA_DIR="tests/data"
CURL_OPTS="-k"  # Accept self-signed certificates

# Non-interactive mode: Set AUTO_MODE=1 to skip all "Press Enter" prompts
AUTO_MODE="${AUTO_MODE:-0}"

# Helper function for pauses
pause_for_user() {
    if [ "$AUTO_MODE" = "1" ]; then
        sleep 1  # Small delay for readability
    else
        echo -e "\n${CYAN}Press Enter to continue...${NC}"
        read -r
    fi
}

# Colors for output
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
MAGENTA='\033[0;35m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Formatting helper
print_header() {
    echo ""
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${CYAN}$1${NC}"
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_section() {
    echo ""
    echo -e "${BOLD}${BLUE}▸ $1${NC}"
    echo -e "${BLUE}────────────────────────────────────────────────────────────────────────────${NC}"
}

print_endpoint() {
    echo ""
    echo -e "${BOLD}${GREEN}Endpoint:${NC} ${YELLOW}$1${NC}"
}

print_explanation() {
    echo -e "${MAGENTA}Purpose:${NC} $1"
}

print_flags() {
    echo -e "${MAGENTA}Parameters:${NC}"
    shift
    for param in "$@"; do
        echo -e "  • $param"
    done
}

print_response() {
    echo -e "${MAGENTA}Response:${NC}"
}

# ============================================================================
# START DEMO
# ============================================================================

echo -e "${BOLD}${CYAN}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║                    MCP TEF API COMPREHENSIVE DEMO                        ║
║                                                                           ║
║                   Model Context Protocol - TEF System                    ║
║              (MCP Analysis, Learning, and Testing Platform)               ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"
echo ""
echo -e "Base URL: ${YELLOW}$BASE_URL${NC}"
echo -e "Data Directory: ${YELLOW}$DATA_DIR${NC}"
echo ""

# ============================================================================
# SERVER STARTUP CHECK
# ============================================================================

echo -e "${CYAN}Checking if API server is running...${NC}"
if curl $CURL_OPTS -s --connect-timeout 2 "$BASE_URL/health" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ API server is running${NC}"
    SERVER_STARTED_BY_SCRIPT=false
else
    echo -e "${YELLOW}⚠ API server not running. Starting it now...${NC}"
    export PYTHONPATH="$(pwd)/src"
    export LOG_LEVEL=INFO
    nohup uv run python -m mcp_tef --port 8000 > .demo-server.log 2>&1 &
    SERVER_PID=$!
    echo $SERVER_PID > .demo-server.pid
    SERVER_STARTED_BY_SCRIPT=true
    
    echo -e "${CYAN}Waiting for server to start (PID: $SERVER_PID)...${NC}"
    for i in {1..15}; do
        if curl $CURL_OPTS -s --connect-timeout 1 "$BASE_URL/health" >/dev/null 2>&1; then
            echo -e "${GREEN}✓ Server started successfully${NC}"
            break
        fi
        if [ $i -eq 15 ]; then
            echo -e "${RED}✗ Server failed to start. Check .demo-server.log for details${NC}"
            exit 1
        fi
        sleep 1
    done
fi
echo ""

# Cleanup function to stop server if we started it
cleanup_server() {
    if [ "$SERVER_STARTED_BY_SCRIPT" = true ] && [ -f .demo-server.pid ]; then
        PID=$(cat .demo-server.pid)
        if kill -0 "$PID" 2>/dev/null; then
            echo ""
            echo -e "${YELLOW}Stopping demo server (PID: $PID)...${NC}"
            kill "$PID" 2>/dev/null || true
            sleep 2
        fi
        rm -f .demo-server.pid
    fi
}
trap cleanup_server EXIT INT TERM

# ============================================================================
# SYNC WITH TOOLHIVE (if available)
# ============================================================================

# Sync server URLs from thv if available
if command -v thv &> /dev/null; then
    echo -e "${YELLOW}Syncing server URLs from ToolHive...${NC}"
    THV_OUTPUT=$(thv ls 2>/dev/null || true)
    if [ -n "$THV_OUTPUT" ]; then
        # Get all servers from API first
        ALL_SERVERS=$(curl $CURL_OPTS -s "$BASE_URL/mcp-servers?limit=100" 2>/dev/null)
        
        echo "$THV_OUTPUT" | tail -n +2 | while read -r line; do
            [ -z "$line" ] && continue
            NAME=$(echo "$line" | awk '{print $1}')
            STATUS=$(echo "$line" | awk '{print $3}')
            URL=$(echo "$line" | awk '{print $4}' | sed 's/#.*//')
            
            if [ "$STATUS" = "running" ] && [ "$NAME" != "toolhive-mcp-optimizer" ]; then
                # Try to update the server URL
                SERVER_ID=$(echo "$ALL_SERVERS" | jq -r ".items[] | select(.name == \"$NAME\") | .id" 2>/dev/null || echo "")
                if [ -n "$SERVER_ID" ]; then
                    curl $CURL_OPTS -s -X PUT "$BASE_URL/mcp-servers/$SERVER_ID" \
                        -H "Content-Type: application/json" \
                        -d "{\"url\": \"$URL\"}" > /dev/null 2>&1
                fi
            fi
        done
        echo -e "${GREEN}✓ Server URLs synced from ToolHive${NC}"
    else
        echo -e "${YELLOW}Note: ToolHive not available, using existing server configurations${NC}"
    fi
else
    echo -e "${YELLOW}Note: ToolHive (thv) not found, using existing server configurations${NC}"
fi
echo ""
pause_for_user

# ============================================================================
# SECTION 1: BASIC ENDPOINTS
# ============================================================================

print_header "SECTION 1: BASIC ENDPOINTS"

# Root Endpoint
print_section "Root Endpoint"
print_endpoint "GET /"
print_explanation "Returns basic information about the API service including name, version, and status."
print_flags "None"
print_response
curl $CURL_OPTS -s "$BASE_URL/" | jq '.'
pause_for_user

# Health Check
print_section "Health Check"
print_endpoint "GET /health"
print_explanation "Simple health check endpoint to verify the API is running and responsive."
print_flags "None"
print_response
curl $CURL_OPTS -s "$BASE_URL/health" | jq '.'
pause_for_user

# ============================================================================
# SECTION 2: MCP SERVER TOOLS & QUALITY
# ============================================================================

print_header "SECTION 2: MCP SERVER TOOLS & QUALITY"

# Note: MCP server registration has been removed. All operations now work directly with server URLs.
echo -e "${YELLOW}Note: MCP server persistence has been removed in favor of URL-based operations.${NC}"
echo -e "${YELLOW}The API loads tools directly from server URLs without requiring registration.${NC}"
echo ""
pause_for_user

# Try to detect running servers from ToolHive for demo
SERVER_URLS=()
if command -v thv &> /dev/null; then
    echo -e "${CYAN}Detecting running MCP servers from ToolHive...${NC}"
    THV_OUTPUT=$(thv ls 2>/dev/null || true)
    if [ -n "$THV_OUTPUT" ]; then
        # Parse running servers (skip toolhive-mcp-optimizer)
        while IFS= read -r line; do
            if echo "$line" | grep -q "running"; then
                server_name=$(echo "$line" | awk '{print $1}')
                if [ "$server_name" != "toolhive-mcp-optimizer" ]; then
                    server_url=$(echo "$line" | awk '{print $4}' | sed 's/#.*//')
                    if [ -n "$server_url" ]; then
                        SERVER_URLS+=("$server_url")
                        echo -e "${GREEN}✓ Found: $server_name ($server_url)${NC}"
                    fi
                fi
            fi
        done < <(echo "$THV_OUTPUT" | tail -n +2)
    fi
fi

# Set up individual server URL variables and JSON array
SERVER_COUNT=${#SERVER_URLS[@]}
if [ $SERVER_COUNT -eq 0 ]; then
    echo -e "${YELLOW}No running MCP servers detected. Using example URLs for demonstration.${NC}"
    echo -e "${YELLOW}Note: Similarity analysis endpoints will show expected error handling.${NC}"
    SERVER_URL_1="http://localhost:3000"
    SERVER_URL_2="http://localhost:3001"
    SERVER_URL_3="http://localhost:3002"
    SERVER_URLS_JSON='["http://localhost:3000","http://localhost:3001","http://localhost:3002"]'
    SERVERS_AVAILABLE=false
else
    echo -e "${GREEN}✓ Found $SERVER_COUNT running server(s)${NC}"
    SERVER_URL_1="${SERVER_URLS[0]}"
    SERVER_URL_2="${SERVER_URLS[1]:-$SERVER_URL_1}"
    SERVER_URL_3="${SERVER_URLS[2]:-$SERVER_URL_1}"
    
    # Create JSON array
    SERVER_URLS_JSON=$(printf '%s\n' "${SERVER_URLS[@]}" | jq -R . | jq -s .)
    
    if [ $SERVER_COUNT -lt 2 ]; then
        echo -e "${YELLOW}Note: Only 1 server available. Some similarity examples will be skipped.${NC}"
    fi
    SERVERS_AVAILABLE=true
fi

# Main demo server for single-server examples
DEMO_SERVER_URL="$SERVER_URL_1"
echo ""
pause_for_user

# Get Server Tools
print_section "Get Tools from a Specific Server URL"
print_endpoint "GET /mcp-servers/tools?server_url={url}"
print_explanation "Lists all tools provided by an MCP server. Loads tools directly from the server URL."
print_flags \
    "server_url (required): The MCP server URL" \
    "offset (optional): Pagination offset" \
    "limit (optional): Maximum number of tools to return"

echo -e "\n${YELLOW}Example: GET /mcp-servers/tools?server_url=$DEMO_SERVER_URL${NC}"

if [ "$SERVERS_AVAILABLE" = true ]; then
    print_response
    curl $CURL_OPTS -s "$BASE_URL/mcp-servers/tools?server_url=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$DEMO_SERVER_URL'))")" | jq '.'
else
    echo -e "\n${YELLOW}Skipped: No running server available${NC}"
fi
pause_for_user

# Get Tool Quality Metrics
print_section "Get Tool Quality Metrics for Server URL(s)"
print_endpoint "GET /mcp-servers/tools/quality?server_urls={urls}"
print_explanation "Analyzes the quality of tools from one or more servers, checking description clarity and parameter definitions."
print_flags \
    "server_urls (required): Comma-separated list of server URLs" \
    "model_provider (required): LLM provider for quality evaluation" \
    "model_name (required): LLM model name"

echo -e "\n${YELLOW}Example: GET /mcp-servers/tools/quality?server_urls=$DEMO_SERVER_URL&model_provider=ollama&model_name=llama3.2:3b${NC}"

if [ "$SERVER_AVAILABLE" = true ]; then
    print_response
    echo -e "${CYAN}(This may take a moment as it performs LLM-based quality evaluation)${NC}"
    curl $CURL_OPTS -s "$BASE_URL/mcp-servers/tools/quality?server_urls=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$DEMO_SERVER_URL'))")&model_provider=ollama&model_name=llama3.2:3b" | jq '.'
else
    echo -e "\n${YELLOW}Skipped: No running server available${NC}"
fi
pause_for_user

# ============================================================================
# SECTION 3: SIMILARITY ANALYSIS
# ============================================================================

print_header "SECTION 3: SIMILARITY ANALYSIS"

echo -e "${YELLOW}Note: Similarity analysis now works directly with server URLs.${NC}"
echo -e "${YELLOW}You provide MCP server URLs via the mcp_server_urls parameter.${NC}"
echo ""
pause_for_user

# Basic Similarity Analysis
print_section "Basic Similarity Analysis (5 tools)"
print_endpoint "POST /similarity/analyze"
print_explanation "Analyzes similarity between tools to find potential overlaps or redundancies. Core feature for optimization."
print_flags \
    "mcp_server_urls (required): Array of MCP server URLs" \
    "similarity_threshold (optional): Minimum similarity score to flag (0.0-1.0, default: 0.7)" \
    "compute_full_similarity (optional): Calculate similarity for all pairs (default: false)" \
    "include_recommendations (optional): Include LLM-generated recommendations (default: false)" \
    "analysis_methods (optional): Methods to use ['embedding', 'description_overlap']" \
    "embedding_model (optional): Specific embedding model to use" \
    "llm_model (optional): Specific LLM model for recommendations"

echo -e "\n${YELLOW}Request Body Example:${NC}"
cat << 'EOF'
{
  "mcp_server_urls": [
    "http://localhost:3000",
      "tools": [
        {
          "name": "search_documents",
          "description": "Search through documents using keywords",
          "parameter": {"query": "Search query"}
        }
      ]
    }
  ],
  "similarity_threshold": 0.7,
  "compute_full_similarity": false
}
EOF

if [ $SERVER_COUNT -ge 2 ]; then
    print_response
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\"],
        \"similarity_threshold\": 0.7,
        \"compute_full_similarity\": false
      }" | jq '.'
else
    echo -e "\n${YELLOW}Skipped: Requires at least 2 running servers (found $SERVER_COUNT)${NC}"
fi
pause_for_user

# Similarity Analysis with 10 Tools
print_section "Similarity Analysis (10 tools, higher threshold)"
print_endpoint "POST /similarity/analyze"
print_explanation "Same analysis but with more tools and a higher similarity threshold (0.75) to reduce false positives."
print_flags \
    "mcp_server_urls: Array of MCP server URLs" \
    "similarity_threshold: 0.75 (higher than default)" \
    "compute_full_similarity: true (computes all pairs, not just flagged)"

echo -e "\n${YELLOW}Using detected servers${NC}"
if [ $SERVER_COUNT -ge 3 ]; then
    print_response
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\", \"$SERVER_URL_3\"],
        \"similarity_threshold\": 0.75,
        \"compute_full_similarity\": true
      }" | jq '.'
else
    echo -e "\n${YELLOW}Skipped: Requires at least 3 running servers (found $SERVER_COUNT)${NC}"
fi
pause_for_user

# Similarity Analysis with 25 Tools
print_section "Similarity Analysis (25 tools, larger dataset)"
print_endpoint "POST /similarity/analyze"
print_explanation "Testing with a larger dataset to demonstrate scalability. Uses even higher threshold (0.8)."
print_flags \
    "mcp_server_urls: Array of MCP server URLs" \
    "similarity_threshold: 0.8 (stricter matching)" \
    "compute_full_similarity: false (performance optimization for large sets)"

echo -e "\n${YELLOW}Using detected servers${NC}"
if [ $SERVER_COUNT -ge 3 ]; then
    print_response
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\", \"$SERVER_URL_3\"],
        \"similarity_threshold\": 0.8,
        \"compute_full_similarity\": false
      }" | jq '.'
else
    echo -e "\n${YELLOW}Skipped: Requires at least 3 running servers (found $SERVER_COUNT)${NC}"
fi
pause_for_user

# Two-Tool Similarity Analysis
print_section "Two-Tool Similarity Analysis"
print_endpoint "POST /similarity/analyze"
print_explanation "Minimal test case with just two tools. Useful for debugging or focused comparison."
print_flags \
    "mcp_server_urls: Array of MCP server URLs" \
    "similarity_threshold: 0.6 (lower threshold for testing)" \
    "compute_full_similarity: true"

echo -e "\n${YELLOW}Using first 2 tools from: $DATA_DIR/mcp_tools_5.json${NC}"
print_response
curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
  -H "Content-Type: application/json" \
  -d "{
    \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\"],
    \"similarity_threshold\": 0.6,
    \"compute_full_similarity\": true
  }" | jq '.'
pause_for_user

# Analysis with Server URLs
print_section "Similarity Analysis Using Server URLs"
print_endpoint "POST /similarity/analyze"
print_explanation "Loads tools directly from MCP server URLs for analysis."
print_flags \
    "mcp_server_urls (required): Array of MCP server URLs" \
    "similarity_threshold (optional): Minimum similarity score (default: 0.7)"

echo -e "\n${YELLOW}Request Body Example:${NC}"
cat << EOF
{
  "mcp_server_urls": ["$DEMO_SERVER_URL", "http://localhost:3001"],
  "similarity_threshold": 0.7
}
EOF

if [ "$SERVER_AVAILABLE" = true ]; then
    print_response
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": [\"$DEMO_SERVER_URL\"],
        \"similarity_threshold\": 0.7
      }" | jq '.'
else
    echo -e "\n${YELLOW}Skipped: No running server available${NC}"
fi
pause_for_user

# Analysis with Recommendations
print_section "Similarity Analysis with LLM Recommendations"
print_endpoint "POST /similarity/analyze"
print_explanation "Includes AI-generated recommendations for handling similar tools. Uses LLM to provide actionable insights."
print_flags \
    "include_recommendations (required): Set to true to enable LLM recommendations" \
    "llm_model (optional): Specify which LLM to use (e.g., 'ebdm/gemma3-enhanced:12b')"

echo -e "\n${YELLOW}Request Body Example:${NC}"
cat << 'EOF'
{
  "mcp_server_urls": ["$SERVER_URL_1", "$SERVER_URL_2"],
  "similarity_threshold": 0.7,
  "include_recommendations": true,
  "llm_model": "ebdm/gemma3-enhanced:12b"
}
EOF

echo -e "\n${YELLOW}Note: This demo uses test data with include_recommendations=true${NC}"
print_response
curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
  -H "Content-Type: application/json" \
  -d "{
    \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\"],
    \"similarity_threshold\": 0.7,
    \"include_recommendations\": true
  }" | jq '.'
pause_for_user

# Similarity Matrix (5 tools)
print_section "Generate Similarity Matrix (5 tools)"
print_endpoint "POST /similarity/matrix"
print_explanation "Generates a full N×N similarity matrix showing relationships between all tools. Useful for visualization."
print_flags \
    "mcp_server_urls: Array of MCP server URLs (same as analyze endpoint)" \
    "similarity_threshold (optional): Threshold for highlighting similarities"

echo -e "\n${YELLOW}Request Body Example:${NC}"
cat << 'EOF'
{
  "mcp_server_urls": ["$SERVER_URL_1", "$SERVER_URL_2"],
  "similarity_threshold": 0.7
}
EOF

print_response
curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/matrix" \
  -H "Content-Type: application/json" \
  -d "{
    \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\"],
    \"similarity_threshold\": 0.7
  }" | jq '.'
pause_for_user

# Similarity Matrix (10 tools)
print_section "Generate Similarity Matrix (10 tools)"
print_endpoint "POST /similarity/matrix"
print_explanation "Matrix with more tools to show how visualization scales."
print_flags \
    "mcp_server_urls: Array of MCP server URLs" \
    "similarity_threshold: 0.75"

echo -e "\n${YELLOW}Using data from: $DATA_DIR/mcp_tools_10.json${NC}"
print_response
curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/matrix" \
  -H "Content-Type: application/json" \
  -d "{
    \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\", \"$SERVER_URL_3\"],
    \"similarity_threshold\": 0.75
  }" | jq '.'
pause_for_user

# Overlap Matrix (5 tools)
print_section "Generate Overlap Matrix with Dimensions (5 tools)"
print_endpoint "POST /similarity/overlap-matrix"
print_explanation "Advanced matrix showing not just similarity scores but dimensional analysis of overlaps (functionality, parameters, etc.)."
print_flags \
    "mcp_server_urls: Array of MCP server URLs (same as analyze endpoint)" \
    "similarity_threshold (optional): Threshold for overlap detection"

echo -e "\n${YELLOW}Request Body Example:${NC}"
cat << 'EOF'
{
  "mcp_server_urls": ["$SERVER_URL_1", "$SERVER_URL_2"],
  "similarity_threshold": 0.7
}
EOF

print_response
curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/overlap-matrix" \
  -H "Content-Type: application/json" \
  -d "{
    \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\"],
    \"similarity_threshold\": 0.7
  }" | jq '.'
pause_for_user

# Overlap Matrix (10 tools)
print_section "Generate Overlap Matrix (10 tools)"
print_endpoint "POST /similarity/overlap-matrix"
print_explanation "Larger overlap matrix to demonstrate multi-tool dimensional analysis."
print_flags \
    "mcp_server_urls: Array of MCP server URLs" \
    "similarity_threshold: 0.75"

echo -e "\n${YELLOW}Using data from: $DATA_DIR/mcp_tools_10.json${NC}"
print_response
curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/overlap-matrix" \
  -H "Content-Type: application/json" \
  -d "{
    \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\", \"$SERVER_URL_3\"],
    \"similarity_threshold\": 0.75
  }" | jq '.'
pause_for_user

# Overlap Matrix (25 tools)
print_section "Generate Overlap Matrix (25 tools, large scale)"
print_endpoint "POST /similarity/overlap-matrix"
print_explanation "Large-scale overlap matrix testing system performance with many tools."
print_flags \
    "mcp_server_urls: Array of MCP server URLs" \
    "similarity_threshold: 0.8"

echo -e "\n${YELLOW}Using data from: $DATA_DIR/mcp_tools_25.json${NC}"
print_response
curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/overlap-matrix" \
  -H "Content-Type: application/json" \
  -d "{
    \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\", \"$SERVER_URL_3\"],
    \"similarity_threshold\": 0.8
  }" | jq '.'
pause_for_user

# Overlap Matrix with Server URLs
print_section "Generate Overlap Matrix with Server URLs"
print_endpoint "POST /similarity/overlap-matrix"
print_explanation "Loads tools from MCP servers and generates overlap analysis. Common use case for comparing server capabilities."
print_flags \
    "mcp_server_urls: Array of MCP server URLs" \
    "similarity_threshold: 0.70"

echo -e "\n${YELLOW}Request Body Example:${NC}"
cat << EOF | jq '.'
{
  "mcp_server_urls": ["$SERVER_URL_1", "$SERVER_URL_2", "$SERVER_URL_3"],
  "similarity_threshold": 0.70
}
EOF

echo -e "\n${YELLOW}Note: Skipping execution in demo (requires multiple running servers).${NC}"
pause_for_user

# Get Recommendations for Tool Pair
print_section "Get Recommendations for Specific Tool Pair"
print_endpoint "GET /similarity/recommendations/{tool_a_id}/{tool_b_id}"
print_explanation "Generates detailed LLM recommendations for handling two similar tools. Provides consolidation strategies."
print_flags \
    "tool_a_id (path): ID of first tool" \
    "tool_b_id (path): ID of second tool" \
    "llm_model (optional query): LLM model to use for recommendations"

echo -e "\n${YELLOW}Note: Requires two valid tool IDs. Skipping in demo due to dependencies.${NC}"
echo -e "\n${YELLOW}Example URL:${NC} GET /similarity/recommendations/server1.tool1/server2.tool2"
pause_for_user

# Analysis Method: Description Overlap
print_section "Similarity Analysis using Description Overlap Method"
print_endpoint "POST /similarity/analyze"
print_explanation "Uses TF-IDF (Term Frequency-Inverse Document Frequency) instead of embeddings. Faster but less semantic understanding."
print_flags \
    "analysis_methods: ['description_overlap'] - specifies TF-IDF method" \
    "similarity_threshold: 0.7"

echo -e "\n${YELLOW}Using data from: $DATA_DIR/mcp_tools_5.json${NC}"
print_response
curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
  -H "Content-Type: application/json" \
  -d "{
    \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\"],
    \"similarity_threshold\": 0.7,
    \"analysis_methods\": [\"description_overlap\"]
  }" | jq '.'
pause_for_user

# Custom Embedding Model
print_section "Similarity Analysis with Custom Embedding Model"
print_endpoint "POST /similarity/analyze"
print_explanation "Uses a specific embedding model (BAAI/bge-base-en-v1.5) instead of the default. Larger model may give better results."
print_flags \
    "embedding_model: 'BAAI/bge-base-en-v1.5' - larger, more accurate model" \
    "similarity_threshold: 0.7"

echo -e "\n${YELLOW}Using data from: $DATA_DIR/mcp_tools_5.json${NC}"
print_response
curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
  -H "Content-Type: application/json" \
  -d "{
    \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\"],
    \"similarity_threshold\": 0.7,
    \"embedding_model\": \"BAAI/bge-base-en-v1.5\"
  }" | jq '.'
pause_for_user

# Complete Feature Demo
print_section "Complete Feature Demo (All Optional Flags)"
print_endpoint "POST /similarity/analyze"
print_explanation "Demonstrates using all available optional parameters together for maximum control."
print_flags \
    "mcp_server_urls: Array of MCP server URLs" \
    "similarity_threshold: 0.7" \
    "compute_full_similarity: true" \
    "include_recommendations: true" \
    "analysis_methods: ['embedding']" \
    "embedding_model: 'BAAI/bge-small-en-v1.5'" \
    "llm_model: 'ebdm/gemma3-enhanced:12b'"

echo -e "\n${YELLOW}Using data from: $DATA_DIR/mcp_tools_5.json${NC}"
print_response
curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
  -H "Content-Type: application/json" \
  -d "{
    \"mcp_server_urls\": [\"$SERVER_URL_1\", \"$SERVER_URL_2\"],
    \"similarity_threshold\": 0.7,
    \"compute_full_similarity\": true,
    \"include_recommendations\": true,
    \"analysis_methods\": [\"embedding\"],
    \"embedding_model\": \"BAAI/bge-small-en-v1.5\",
    \"llm_model\": \"ebdm/gemma3-enhanced:12b\"
  }" | jq '.'
pause_for_user

# Note: tool_list format removed
# PR #71 simplified the API to only use mcp_server_urls for better separation of concerns
# All similarity tests above use the standard mcp_server_urls format
echo -e "${YELLOW}Note: Embedded tool format (tool_list/server_list) removed in PR #71${NC}"
echo -e "${YELLOW}API now uses mcp_server_urls exclusively (see tests above)${NC}"
echo ""
pause_for_user

# Specific Server Comparisons
print_section "Real-World Comparison: Multiple Server URLs"
print_endpoint "POST /similarity/analyze"
print_explanation "Practical example comparing multiple servers to find overlapping capabilities."
print_flags \
    "mcp_server_urls: Array of MCP server URLs" \
    "similarity_threshold: 0.70"

echo -e "\n${YELLOW}Request Body Example:${NC}"
cat << 'EOF'
{
  "mcp_server_urls": [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002"
  ],
  "similarity_threshold": 0.70
}
EOF

echo -e "\n${YELLOW}Note: Skipping execution in demo (requires multiple running servers).${NC}"
echo -e "${YELLOW}This would show which operations overlap across the specified servers.${NC}"
pause_for_user

# ============================================================================
# SECTION 5: TEST CASE MANAGEMENT
# ============================================================================

print_header "SECTION 5: TEST CASE MANAGEMENT"

# Create Test Case
print_section "Create a Test Case"
print_endpoint "POST /test-cases"
print_explanation "Creates a test case to evaluate tool selection. Test cases verify that the LLM chooses the right tool for a given query."
print_flags \
    "name (required): Test case name" \
    "query (required): User query to evaluate" \
    "expected_mcp_server_name (required): Expected MCP server name" \
    "expected_tool_name (required): Expected tool name" \
    "expected_parameters (optional): Expected parameter values" \
    "available_mcp_servers (required): List of MCP server URLs available to LLM"

# Set up test case data based on server availability
DEMO_TOOL="example_tool"
DEMO_PARAMS='{"param": "value"}'
DEMO_QUERY="Example query for demonstration"

echo -e "\n${YELLOW}Request Body Example:${NC}"
cat << EOF | jq '.'
{
  "name": "Test tool selection",
  "query": "$DEMO_QUERY",
  "expected_mcp_server_name": "example-server",
  "expected_tool_name": "$DEMO_TOOL",
  "expected_parameters": $DEMO_PARAMS,
  "available_mcp_servers": ["$DEMO_SERVER_URL"]
}
EOF

if [ "$SERVER_AVAILABLE" = true ]; then
    echo -e "\n${YELLOW}Attempting to create test case...${NC}"
    print_response
    TEST_CASE_DATA=$(cat << EOF
{
  "name": "Test tool selection",
  "query": "$DEMO_QUERY",
  "expected_mcp_server_name": "example-server",
  "expected_tool_name": "$DEMO_TOOL",
  "expected_parameters": $DEMO_PARAMS,
  "available_mcp_servers": ["$DEMO_SERVER_URL"]
}
EOF
    )
    TEST_CASE_RESPONSE=$(curl $CURL_OPTS -s -X POST "$BASE_URL/test-cases" \
      -H "Content-Type: application/json" \
      -d "$TEST_CASE_DATA")
    echo "$TEST_CASE_RESPONSE" | jq '.'

    TEST_CASE_ID=$(echo "$TEST_CASE_RESPONSE" | jq -r '.id // empty')
    if [ -z "$TEST_CASE_ID" ]; then
        echo -e "\n${YELLOW}Note: Test case creation requires MCP servers to be actively running and reachable.${NC}"
        echo -e "${YELLOW}For demo purposes, the remaining test case operations will be skipped.${NC}"
        SKIP_TEST_CASES=true
    else
        echo -e "\n${GREEN}✓ Test case created with ID: $TEST_CASE_ID${NC}"
        SKIP_TEST_CASES=false
    fi
else
    echo -e "\n${YELLOW}Skipped: No running server available${NC}"
    SKIP_TEST_CASES=true
fi
pause_for_user

# List Test Cases
print_section "List All Test Cases"
print_endpoint "GET /test-cases"
print_explanation "Lists all test cases in the system with pagination support."
print_flags \
    "skip (optional): Pagination offset" \
    "limit (optional): Maximum number of test cases to return" \
    "category (optional): Filter by category"

if [ "$SKIP_TEST_CASES" = true ]; then
    echo -e "\n${YELLOW}Showing endpoint structure (no test cases created):${NC}"
    echo -e "${YELLOW}Example response structure:${NC}"
    cat << 'EOF'
{
  "items": [],
  "total": 0,
  "offset": 0,
  "limit": 100
}
EOF
else
    print_response
    curl $CURL_OPTS -s "$BASE_URL/test-cases" | jq '.'
fi
pause_for_user

# Get Test Case Details
print_section "Get Test Case Details"
print_endpoint "GET /test-cases/{test_case_id}"
print_explanation "Retrieves detailed information about a specific test case."
print_flags \
    "test_case_id (path): The unique ID of the test case"

if [ "$SKIP_TEST_CASES" = true ] || [ -z "$TEST_CASE_ID" ]; then
    echo -e "\n${YELLOW}Skipped: No test case available${NC}"
    echo -e "${YELLOW}Example: GET /test-cases/{id}${NC}"
else
    print_response
    curl $CURL_OPTS -s "$BASE_URL/test-cases/$TEST_CASE_ID" | jq '.'
fi
pause_for_user

# Update Test Case
print_section "Update Test Case"
print_endpoint "PUT /test-cases/{test_case_id}"
print_explanation "Note: PUT is used to update an existing test case. Check API docs for updateable fields."
print_flags \
    "test_case_id (path): The unique ID of the test case"

echo -e "\n${YELLOW}Note: Test case update functionality - refer to API docs for updateable fields.${NC}"
echo -e "${YELLOW}Example URL: PUT /test-cases/{id}${NC}"
pause_for_user

# ============================================================================
# SECTION 6: TEST RUNS & EVALUATION
# ============================================================================

print_header "SECTION 6: TEST RUNS & EVALUATION"

# Create and Execute Test Run
print_section "Create and Execute a Test Run"
print_endpoint "POST /test-cases/{test_case_id}/run"
print_explanation "Executes a test run for a specific test case, evaluating how well the LLM selects tools. Core evaluation feature."
print_flags \
    "test_case_id (path): The test case ID to run" \
    "model_settings (optional): LLM model configuration (provider, name, temperature, etc.)"

echo -e "\n${YELLOW}Request Body Example:${NC}"
cat << 'EOF'
{
  "model_settings": {
    "provider": "ollama",
    "name": "llama3.2:3b",
    "temperature": 0.7
  }
}
EOF

if [ "$SKIP_TEST_CASES" = true ] || [ -z "$TEST_CASE_ID" ]; then
    echo -e "\n${YELLOW}Skipped: No test case available to run${NC}"
    echo -e "${YELLOW}Example: POST /test-cases/{id}/run${NC}"
    TEST_RUN_ID=""
else
    print_response
    TEST_RUN_RESPONSE=$(curl $CURL_OPTS -s -X POST "$BASE_URL/test-cases/$TEST_CASE_ID/run" \
      -H "Content-Type: application/json" \
      -d '{
        "model_settings": {
          "provider": "ollama",
          "name": "llama3.2:3b",
          "temperature": 0.7
        }
      }')
    echo "$TEST_RUN_RESPONSE" | jq '.'

    TEST_RUN_ID=$(echo "$TEST_RUN_RESPONSE" | jq -r '.id // empty')
    if [ -z "$TEST_RUN_ID" ]; then
        echo -e "\n${YELLOW}Note: Test run creation may have failed or requires LLM configuration.${NC}"
    else
        echo -e "\n${GREEN}✓ Test run created with ID: $TEST_RUN_ID${NC}"
    fi
fi
pause_for_user

# Get Test Case with Runs
print_section "Get Test Case (includes associated runs)"
print_endpoint "GET /test-cases/{test_case_id}"
print_explanation "Test cases include their associated test runs. There's no separate list-all-runs endpoint."
print_flags \
    "test_case_id (path): The test case ID"

if [ "$SKIP_TEST_CASES" = true ] || [ -z "$TEST_CASE_ID" ]; then
    echo -e "\n${YELLOW}Skipped: No test case available${NC}"
else
    print_response
    curl $CURL_OPTS -s "$BASE_URL/test-cases/$TEST_CASE_ID" | jq '.'
fi
pause_for_user

# Get Test Run Details
print_section "Get Test Run Details"
print_endpoint "GET /test-runs/{test_run_id}"
print_explanation "Retrieves detailed information about a specific test run including configuration and status."
print_flags \
    "test_run_id (path): The unique ID of the test run"

if [ "$SKIP_TEST_CASES" = true ] || [ -z "$TEST_RUN_ID" ]; then
    echo -e "\n${YELLOW}Skipped: No test run available${NC}"
    echo -e "${YELLOW}Example: GET /test-runs/{id}${NC}"
else
    print_response
    curl $CURL_OPTS -s "$BASE_URL/test-runs/$TEST_RUN_ID" | jq '.'
fi
pause_for_user

# Get Test Run Result
print_section "Get Test Run Evaluation Result"
print_endpoint "GET /test-runs/{test_run_id}/result"
print_explanation "Retrieves detailed evaluation result with parameter validation. Only available for completed test runs."
print_flags \
    "test_run_id (path): The unique ID of the test run"

if [ "$SKIP_TEST_CASES" = true ] || [ -z "$TEST_RUN_ID" ]; then
    echo -e "\n${YELLOW}Skipped: No test run available${NC}"
    echo -e "${YELLOW}Note: This endpoint requires the test run to be completed first.${NC}"
    echo -e "${YELLOW}Example: GET /test-runs/{id}/result${NC}"
else
    print_response
    echo -e "${YELLOW}Note: This requires the test run to be completed and may take a moment.${NC}"
    curl $CURL_OPTS -s "$BASE_URL/test-runs/$TEST_RUN_ID/result" | jq '.'
fi
pause_for_user

# ============================================================================
# SECTION 7: METRICS & ANALYTICS
# ============================================================================

print_header "SECTION 7: METRICS & ANALYTICS"

# Get Metrics Summary
print_section "Get Metrics Summary"
print_endpoint "GET /metrics/summary"
print_explanation "Retrieves aggregated metrics across test runs with optional filtering by test cases or date range."
print_flags \
    "test_case_ids (optional query): Filter by specific test case IDs" \
    "start_date (optional query): Filter test runs after this date" \
    "end_date (optional query): Filter test runs before this date"
print_response
curl $CURL_OPTS -s "$BASE_URL/metrics/summary" | jq '.'
pause_for_user

# Get Filtered Metrics
print_section "Get Filtered Metrics Summary"
print_endpoint "GET /metrics/summary?test_case_ids={ids}"
print_explanation "Example of filtering metrics by specific test case IDs."
print_flags \
    "test_case_ids (query): Test case IDs to filter by"

echo -e "\n${YELLOW}Example: GET /metrics/summary?test_case_ids=$TEST_CASE_ID${NC}"
print_response
curl $CURL_OPTS -s "$BASE_URL/metrics/summary?test_case_ids=$TEST_CASE_ID" | jq '.'
pause_for_user

# ============================================================================
# SECTION 8: CLEANUP (Optional)
# ============================================================================

print_header "SECTION 8: CLEANUP & DELETE OPERATIONS"

# Delete Test Run
print_section "Delete Test Run"
print_endpoint "DELETE /test-runs/{test_run_id}"
print_explanation "Deletes a test run and all associated results. Note: Test runs are typically managed via test cases."
print_flags \
    "test_run_id (path): The unique ID of the test run to delete"

echo -e "\n${YELLOW}Note: Test runs are associated with test cases. Deleting the test case will remove its runs.${NC}"
echo -e "${YELLOW}Individual test run deletion may not be available in the current API.${NC}"
pause_for_user

# Delete Test Case
print_section "Delete Test Case"
print_endpoint "DELETE /test-cases/{test_case_id}"
print_explanation "Deletes a test case from the system."
print_flags \
    "test_case_id (path): The unique ID of the test case to delete"

if [ "$SKIP_TEST_CASES" = true ] || [ -z "$TEST_CASE_ID" ]; then
    echo -e "\n${YELLOW}Skipped: No test case to delete${NC}"
    echo -e "${YELLOW}Example: DELETE /test-cases/{id}${NC}"
else
    echo -e "\n${YELLOW}Executing deletion...${NC}"
    curl $CURL_OPTS -s -X DELETE "$BASE_URL/test-cases/$TEST_CASE_ID"
    echo -e "${GREEN}✓ Test case deleted${NC}"
fi
pause_for_user

# Note about MCP server lifecycle
print_section "MCP Server Lifecycle"
echo -e "${YELLOW}Note: MCP server persistence has been removed from the API.${NC}"
echo -e "${YELLOW}Servers are no longer registered/stored in the database.${NC}"
echo -e "${YELLOW}All operations work directly with server URLs.${NC}"
echo ""
echo -e "${CYAN}Benefits:${NC}"
echo "  • No pre-registration required"
echo "  • Always up-to-date tool definitions"
echo "  • Simpler API surface"
echo "  • Reduced database complexity"
pause_for_user

# ============================================================================
# SECTION 9: ADVANCED USAGE PATTERNS
# ============================================================================

print_header "SECTION 9: ADVANCED USAGE PATTERNS FOR UI IMPLEMENTATION"

print_section "Common UI Workflows"
echo -e "${MAGENTA}Workflow 1: New User Onboarding${NC}"
echo "  1. GET /health - Check API availability"
echo "  2. GET / - Get API information"
echo "  3. User provides their MCP server URLs"
echo "  4. GET /mcp-servers/tools?server_url={url} - Preview available tools"
echo ""

echo -e "${MAGENTA}Workflow 2: Tool Similarity Dashboard${NC}"
echo "  1. User provides server URLs to compare"
echo "  2. POST /similarity/analyze - Run similarity analysis with mcp_server_urls"
echo "  3. POST /similarity/matrix - Generate visualization data"
echo "  4. POST /similarity/overlap-matrix - Show dimensional overlaps"
echo ""

echo -e "${MAGENTA}Workflow 3: Evaluation Pipeline${NC}"
echo "  1. POST /test-cases - Create test cases (with server URLs)"
echo "  2. POST /test-cases/{id}/run - Execute evaluation"
echo "  3. GET /test-runs/{id}/result - Get results"
echo "  4. GET /metrics/summary - Show overall performance"
echo ""

echo -e "${MAGENTA}Workflow 4: Tool Quality Analysis${NC}"
echo "  1. User provides server URLs"
echo "  2. GET /mcp-servers/tools?server_url={url} - View tools"
echo "  3. GET /mcp-servers/tools/quality?server_urls={urls} - Check quality"
echo "  4. Review recommendations and improve tool definitions"
echo ""

pause_for_user

print_section "Important API Patterns for UI Development"
echo ""
echo -e "${MAGENTA}1. Pagination${NC}"
echo "   Most list endpoints support skip/limit parameters:"
echo "   GET /tools?skip=0&limit=20"
echo ""

echo -e "${MAGENTA}2. Server URL Parameters${NC}"
echo "   Use server URL query parameters:"
echo "   GET /mcp-servers/tools?server_url=http://localhost:3000"
echo ""

echo -e "${MAGENTA}3. Error Handling${NC}"
echo "   All endpoints return consistent error format:"
echo '   {"detail": "Error message", "status_code": 400}'
echo ""

echo -e "${MAGENTA}4. Async Operations${NC}"
echo "   Some operations (test runs, similarity analysis) may take time."
echo "   Consider showing loading states in the UI."
echo ""

echo -e "${MAGENTA}5. Content Types${NC}"
echo "   All POST/PUT requests require: Content-Type: application/json"
echo ""

echo -e "${MAGENTA}6. CORS${NC}"
echo "   API supports CORS for web-based UIs."
echo ""

pause_for_user

print_section "Response Structure Examples"
echo ""
echo -e "${MAGENTA}List Response Pattern:${NC}"
cat << 'EOF'
{
  "items": [...],
  "total": 100,
  "skip": 0,
  "limit": 20
}
EOF

echo ""
echo -e "${MAGENTA}Single Resource Response:${NC}"
cat << 'EOF'
{
  "id": "resource-id",
  "name": "resource-name",
  "created_at": "2024-11-05T10:00:00Z",
  ...
}
EOF

echo ""
echo -e "${MAGENTA}Similarity Analysis Response:${NC}"
cat << 'EOF'
{
  "tool_ids": ["tool1", "tool2"],
  "flagged_pairs": [
    {
      "tool_a_id": "tool1",
      "tool_b_id": "tool2",
      "similarity_score": 0.85,
      "recommendation": "..."
    }
  ],
  "analysis_method": "embedding",
  "embedding_model": "BAAI/bge-small-en-v1.5"
}
EOF

pause_for_user

# ============================================================================
# FINALE
# ============================================================================

print_header "DEMO COMPLETE!"

echo ""
echo -e "${GREEN}✓ All API endpoints have been demonstrated${NC}"
echo ""
echo -e "${BOLD}${CYAN}Quick Reference Summary:${NC}"
echo ""
echo -e "${BOLD}Basic Endpoints:${NC}"
echo "  GET  /              - API info"
echo "  GET  /health        - Health check"
echo ""
echo -e "${BOLD}MCP Servers & Tools:${NC}"
echo "  GET    /mcp-servers/tools?server_url={url}                - Load tools from URL"
echo "  GET    /mcp-servers/tools/quality?server_urls={urls}...   - Tool quality metrics"
echo ""
echo -e "${BOLD}Similarity Analysis:${NC}"
echo "  POST /similarity/analyze        - Analyze tool similarities"
echo "  POST /similarity/matrix         - Generate similarity matrix"
echo "  POST /similarity/overlap-matrix - Generate overlap matrix"
echo "  GET  /similarity/recommendations/{id1}/{id2} - Get recommendations"
echo ""
echo -e "${BOLD}Test Cases:${NC}"
echo "  GET    /test-cases     - List test cases"
echo "  POST   /test-cases     - Create test case"
echo "  GET    /test-cases/{id} - Get test case"
echo "  PUT    /test-cases/{id} - Update test case"
echo "  DELETE /test-cases/{id} - Delete test case"
echo ""
echo -e "${BOLD}Test Runs:${NC}"
echo "  POST   /test-cases/{id}/run  - Create and execute test run"
echo "  GET    /test-runs/{id}       - Get test run details"
echo "  GET    /test-runs/{id}/result - Get evaluation result"
echo ""
echo -e "${BOLD}Metrics:${NC}"
echo "  GET  /metrics/summary                    - Get metrics summary"
echo "  GET  /metrics/summary?test_case_ids={id} - Filtered metrics"
echo ""
echo -e "${BOLD}Documentation:${NC}"
echo "  Swagger UI: ${YELLOW}$BASE_URL/docs${NC}"
echo "  ReDoc:      ${YELLOW}$BASE_URL/redoc${NC}"
echo ""
echo -e "${CYAN}For UI implementation, refer to Section 9 for workflows and patterns.${NC}"
echo ""
echo -e "${GREEN}Happy building! 🚀${NC}"
echo ""

