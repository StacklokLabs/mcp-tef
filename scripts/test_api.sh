#!/bin/bash

# Test script for MCP TEF API
# Uses test data files to make curl requests to the running server

set -e

# Configuration
# Default to HTTPS since TLS is enabled by default (issue #51)
# Use -k flag to accept self-signed certificates
BASE_URL="${BASE_URL:-https://localhost:8000}"
DATA_DIR="tests/data"
CURL_OPTS="-k"  # Accept self-signed certificates

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MCP TEF API Test Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Base URL: $BASE_URL"
echo "Data Directory: $DATA_DIR"
echo ""

# Auto-detect running MCP servers for similarity tests
echo -e "${BLUE}Detecting running MCP servers...${NC}"
if command -v thv &> /dev/null; then
    MCP_SERVERS=$(thv ls 2>/dev/null | jq -r '.[] | select(.status == "running") | .url' 2>/dev/null | head -3)
    SERVER_COUNT=$(echo "$MCP_SERVERS" | grep -c "^http" 2>/dev/null || echo "0")
    SERVER_COUNT=${SERVER_COUNT##*$'\n'}  # Take last line if multiple
    
    if [ "$SERVER_COUNT" -ge 2 ] 2>/dev/null; then
        # Build JSON array of server URLs
        MCP_SERVER_URLS=$(echo "$MCP_SERVERS" | jq -R . | jq -s .)
        echo -e "${GREEN}Found $SERVER_COUNT running MCP servers:${NC}"
        echo "$MCP_SERVERS" | while read -r url; do echo "  - $url"; done
        HAVE_MCP_SERVERS=true
    else
        echo -e "${YELLOW}Less than 2 MCP servers running. Similarity tests will be skipped.${NC}"
        echo -e "${YELLOW}Start MCP servers to enable similarity tests.${NC}"
        HAVE_MCP_SERVERS=false
    fi
else
    echo -e "${YELLOW}ToolHive (thv) not found. Similarity tests will be skipped.${NC}"
    echo -e "${YELLOW}Install ToolHive or set MCP_SERVER_URLS env var to enable similarity tests.${NC}"
    HAVE_MCP_SERVERS=false
fi

# Allow manual override via environment variable
if [ -n "$MCP_SERVER_URLS" ]; then
    echo -e "${GREEN}Using manually provided MCP_SERVER_URLS${NC}"
    HAVE_MCP_SERVERS=true
fi
echo ""

# Test 1: Health Check
echo -e "${GREEN}1. Health Check${NC}"
echo -e "${YELLOW}GET $BASE_URL/health${NC}"
curl $CURL_OPTS -s "$BASE_URL/health" | jq '.'
echo ""
echo ""

# Test 2: Root endpoint
echo -e "${GREEN}2. Root Endpoint${NC}"
echo -e "${YELLOW}GET $BASE_URL/${NC}"
curl $CURL_OPTS -s "$BASE_URL/" | jq '.'
echo ""
echo ""

# Test 3: Similarity Analysis
echo -e "${GREEN}3. Similarity Analysis${NC}"
echo -e "${YELLOW}POST $BASE_URL/similarity/analyze${NC}"
if [ "$HAVE_MCP_SERVERS" = true ]; then
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": $MCP_SERVER_URLS,
        \"similarity_threshold\": 0.7,
        \"compute_full_similarity\": false
      }" | jq '.'
else
    echo -e "${YELLOW}Skipped: No MCP servers available${NC}"
fi
echo ""
echo ""

# Test 4: Similarity Matrix
echo -e "${GREEN}4. Similarity Matrix${NC}"
echo -e "${YELLOW}POST $BASE_URL/similarity/matrix${NC}"
if [ "$HAVE_MCP_SERVERS" = true ]; then
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/matrix" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": $MCP_SERVER_URLS,
        \"similarity_threshold\": 0.7
      }" | jq '.'
else
    echo -e "${YELLOW}Skipped: No MCP servers available${NC}"
fi
echo ""
echo ""

# Test 5: Overlap Matrix
echo -e "${GREEN}5. Overlap Matrix${NC}"
echo -e "${YELLOW}POST $BASE_URL/similarity/overlap-matrix${NC}"
if [ "$HAVE_MCP_SERVERS" = true ]; then
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/overlap-matrix" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": $MCP_SERVER_URLS,
        \"similarity_threshold\": 0.7
      }" | jq '.'
else
    echo -e "${YELLOW}Skipped: No MCP servers available${NC}"
fi
echo ""
echo ""

# Test 6: Similarity Analysis with Higher Threshold
echo -e "${GREEN}6. Similarity Analysis with Higher Threshold${NC}"
echo -e "${YELLOW}POST $BASE_URL/similarity/analyze${NC}"
if [ "$HAVE_MCP_SERVERS" = true ]; then
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": $MCP_SERVER_URLS,
        \"similarity_threshold\": 0.75,
        \"compute_full_similarity\": true
      }" | jq '.'
else
    echo -e "${YELLOW}Skipped: No MCP servers available${NC}"
fi
echo ""
echo ""

# Test 7: Similarity Matrix with Higher Threshold
echo -e "${GREEN}7. Similarity Matrix with Higher Threshold${NC}"
echo -e "${YELLOW}POST $BASE_URL/similarity/matrix${NC}"
if [ "$HAVE_MCP_SERVERS" = true ]; then
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/matrix" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": $MCP_SERVER_URLS,
        \"similarity_threshold\": 0.75
      }" | jq '.'
else
    echo -e "${YELLOW}Skipped: No MCP servers available${NC}"
fi
echo ""
echo ""

# Test 8: Overlap Matrix with Higher Threshold
echo -e "${GREEN}8. Overlap Matrix with Higher Threshold${NC}"
echo -e "${YELLOW}POST $BASE_URL/similarity/overlap-matrix${NC}"
if [ "$HAVE_MCP_SERVERS" = true ]; then
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/overlap-matrix" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": $MCP_SERVER_URLS,
        \"similarity_threshold\": 0.75
      }" | jq '.'
else
    echo -e "${YELLOW}Skipped: No MCP servers available${NC}"
fi
echo ""
echo ""

# Test 9: Similarity Analysis with Stricter Threshold
echo -e "${GREEN}9. Similarity Analysis with Stricter Threshold${NC}"
echo -e "${YELLOW}POST $BASE_URL/similarity/analyze${NC}"
if [ "$HAVE_MCP_SERVERS" = true ]; then
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": $MCP_SERVER_URLS,
        \"similarity_threshold\": 0.8,
        \"compute_full_similarity\": false
      }" | jq '.'
else
    echo -e "${YELLOW}Skipped: No MCP servers available${NC}"
fi
echo ""
echo ""

# Tests 10-16: Additional Similarity Variations
# Note: Tests 3-9 cover the main similarity endpoints with real MCP servers
# These additional tests demonstrate various options and parameters
echo -e "${GREEN}10-16. Additional Similarity Test Variations${NC}"
if [ "$HAVE_MCP_SERVERS" = true ]; then
    echo -e "${YELLOW}Testing with detected MCP servers...${NC}"
    echo -e "${YELLOW}Note: These tests exercise various API parameters${NC}"
    echo ""
    # Test with recommendations
    echo "  - With recommendations enabled"
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": $MCP_SERVER_URLS,
        \"similarity_threshold\": 0.7,
        \"include_recommendations\": true
      }" > /dev/null 2>&1 && echo "    ✓ Success" || echo "    ✗ Failed"
    
    # Test with description overlap method
    echo "  - With description_overlap analysis method"
    curl $CURL_OPTS -s -X POST "$BASE_URL/similarity/analyze" \
      -H "Content-Type: application/json" \
      -d "{
        \"mcp_server_urls\": $MCP_SERVER_URLS,
        \"similarity_threshold\": 0.7,
        \"analysis_methods\": [\"description_overlap\"]
      }" > /dev/null 2>&1 && echo "    ✓ Success" || echo "    ✗ Failed"
else
    echo -e "${YELLOW}Skipped: No MCP servers available${NC}"
    echo -e "${YELLOW}Tests 3-9 already cover main endpoints when servers are available${NC}"
fi
echo ""
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}All API Tests Complete${NC}"
echo -e "${BLUE}========================================${NC}"

