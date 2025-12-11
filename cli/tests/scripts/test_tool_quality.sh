#!/usr/bin/env bash
#
# End-to-end test for the tool-quality CLI command.
#
# Prerequisites:
#   - thv (ToolHive CLI) installed and configured
#   - mtef installed
#   - Docker running
#   - TEF_API_KEY or --api-key for LLM provider
#
# Usage:
#   ./test_tool_quality.sh [--api-key <key>] [--model-provider <provider>] [--model-name <model>]
#

set -euo pipefail

# Source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Default configuration
MODEL_PROVIDER="${MODEL_PROVIDER:-openrouter}"
MODEL_NAME="${MODEL_NAME:-anthropic/claude-sonnet-4.5}"
API_KEY="${TEF_API_KEY:-}"
TEF_PORT="${TEF_PORT:-8000}"
TEF_CONTAINER_NAME="mcp-tef-e2e-test"
MCP_SERVER_NAME="fetch"
LOCAL_IMAGE=""  # Will be set after building

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --api-key)
            API_KEY="$2"
            shift 2
            ;;
        --model-provider)
            MODEL_PROVIDER="$2"
            shift 2
            ;;
        --model-name)
            MODEL_NAME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Cleanup function - runs on exit
cleanup() {
    log_info "Cleaning up..."
    remove_mcp_server "${MCP_SERVER_NAME}" 2>/dev/null || true
    force_remove_mcp_tef "${TEF_CONTAINER_NAME}" 2>/dev/null || true
    log_info "Cleanup complete"
}

trap cleanup EXIT

# Validate prerequisites
log_info "Checking prerequisites..."

if ! check_docker; then
    exit 1
fi

if ! check_thv; then
    exit 1
fi

if ! check_mcp_tef_cli; then
    exit 1
fi

if [[ -z "${API_KEY}" ]]; then
    log_error "API key required. Set TEF_API_KEY or use --api-key"
    exit 1
fi

log_success "Prerequisites OK"

# Step 1: Build local Docker image
log_info "Step 1: Building local Docker image..."

LOCAL_IMAGE=$(build_mcp_tef_image) || exit 1

# Step 2: Deploy MCP server using thv
log_info "Step 2: Deploying MCP server..."

if ! deploy_mcp_server "${MCP_SERVER_NAME}" 30; then
    exit 1
fi

# Step 3: Get MCP server URL from thv list
log_info "Step 3: Getting MCP server URL..."

MCP_SERVER_URL_RAW=$(get_mcp_server_url "${MCP_SERVER_NAME}") || exit 1
MCP_SERVER_URL=$(get_mcp_server_url "${MCP_SERVER_NAME}" "true") || exit 1

log_info "MCP server URL (raw): ${MCP_SERVER_URL_RAW}"
log_info "MCP server URL (for Docker): ${MCP_SERVER_URL}"

# Step 4: Deploy mcp-tef
log_info "Step 4: Deploying mcp-tef container..."

if ! deploy_mcp_tef "${TEF_CONTAINER_NAME}" "${LOCAL_IMAGE}" \
    --force \
    --port "${TEF_PORT}" \
    --health-check \
    --insecure \
    --detach; then
    exit 1
fi

# Step 5: Run tool-quality evaluation
log_info "Step 5: Evaluating tool quality for ${MCP_SERVER_NAME}..."

# Capture both stdout and stderr, allowing non-zero exit
RESULT=$(mtef tool-quality \
    --container-name "${TEF_CONTAINER_NAME}" \
    --server-urls "${MCP_SERVER_URL}" \
    --model-provider "${MODEL_PROVIDER}" \
    --model-name "${MODEL_NAME}" \
    --api-key "${API_KEY}" \
    --insecure \
    --format json \
    --timeout 120 2>&1) || EXIT_CODE=$?

EXIT_CODE=${EXIT_CODE:-0}

# Log the raw result for debugging
log_info "Raw tool quality result:"
echo "${RESULT}"

# Step 6: Validate results
log_info "Step 6: Validating results..."

if [[ ${EXIT_CODE} -ne 0 ]]; then
    log_error "tool-quality command failed with exit code ${EXIT_CODE}"
    exit 1
fi

# Parse JSON and validate structure
if ! echo "${RESULT}" | jq -e '.results' > /dev/null 2>&1; then
    log_error "Invalid response: missing 'results' field"
    echo "${RESULT}"
    exit 1
fi

# Check that we got at least one tool result
TOOL_COUNT=$(echo "${RESULT}" | jq '.results | length')
if [[ "${TOOL_COUNT}" -lt 1 ]]; then
    log_error "No tools evaluated (expected at least 1)"
    exit 1
fi

log_info "Evaluated ${TOOL_COUNT} tool(s)"

# Validate each tool has required fields
INVALID_TOOLS=$(echo "${RESULT}" | jq '[.results[] | select(
    .tool_name == null or
    .evaluation_result.clarity.score == null or
    .evaluation_result.completeness.score == null or
    .evaluation_result.conciseness.score == null
)] | length')

if [[ "${INVALID_TOOLS}" -gt 0 ]]; then
    log_error "${INVALID_TOOLS} tool(s) have missing evaluation fields"
    exit 1
fi

# Check for errors in response
ERRORS=$(echo "${RESULT}" | jq '.errors // []')
if [[ "${ERRORS}" != "null" && "${ERRORS}" != "[]" ]]; then
    log_warn "Evaluation returned errors: ${ERRORS}"
fi

# Validate scores are in valid range (1-10)
INVALID_SCORES=$(echo "${RESULT}" | jq '[.results[].evaluation_result |
    .clarity.score, .completeness.score, .conciseness.score |
    select(. < 1 or . > 10)] | length')

if [[ "${INVALID_SCORES}" -gt 0 ]]; then
    log_error "Found ${INVALID_SCORES} score(s) outside valid range (1-10)"
    exit 1
fi

# Print summary
log_info "=== Test Summary ==="
echo "${RESULT}" | jq -r '.results[] | "  \(.tool_name): clarity=\(.evaluation_result.clarity.score)/10, completeness=\(.evaluation_result.completeness.score)/10, conciseness=\(.evaluation_result.conciseness.score)/10"'

log_success "All validations passed!"
exit 0
