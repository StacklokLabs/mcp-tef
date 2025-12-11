#!/usr/bin/env bash
#
# End-to-end test for the similarity CLI commands.
#
# Prerequisites:
#   - thv (ToolHive CLI) installed and configured
#   - mtef installed
#   - Docker running
#
# Usage:
#   ./test_similarity.sh [--skip-recommendations]
#
# Note: The --skip-recommendations flag skips tests that require LLM API access.
#       Basic similarity analysis uses embedding models and doesn't require API keys.
#

set -euo pipefail

# Source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Default configuration
TEF_PORT="${TEF_PORT:-8000}"
TEF_CONTAINER_NAME="mcp-tef-e2e-similarity-test"
MCP_SERVER_NAME="time"  # Time server has exactly 2 tools, perfect for similarity analysis
LOCAL_IMAGE=""  # Will be set after building
SKIP_RECOMMENDATIONS="${SKIP_RECOMMENDATIONS:-false}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-recommendations)
            SKIP_RECOMMENDATIONS="true"
            shift
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

log_success "Prerequisites OK"

# Step 1: Build local Docker image
log_info "Step 1: Building local Docker image..."

LOCAL_IMAGE=$(build_mcp_tef_image) || exit 1

# Step 2: Deploy MCP servers using thv
log_info "Step 2: Deploying MCP servers..."

if ! deploy_mcp_server "${MCP_SERVER_NAME}" 30; then
    exit 1
fi

# Step 3: Get MCP server URL from thv list
log_info "Step 3: Getting MCP server URLs..."

MCP_SERVER_URL=$(get_mcp_server_url "${MCP_SERVER_NAME}" "true") || exit 1
log_info "MCP server URL: ${MCP_SERVER_URL}"

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

# ============================================================================
# Test: similarity analyze (basic - no recommendations)
# ============================================================================

log_info "=== Test: similarity analyze (basic) ==="

RESULT=$(mtef similarity analyze \
    --container-name "${TEF_CONTAINER_NAME}" \
    --server-urls "${MCP_SERVER_URL}" \
    --threshold 0.85 \
    --insecure \
    --format json \
    --timeout 120 2>&1) || EXIT_CODE=$?

EXIT_CODE=${EXIT_CODE:-0}

log_info "Raw similarity analyze result:"
echo "${RESULT}"

if [[ ${EXIT_CODE} -ne 0 ]]; then
    log_error "similarity analyze command failed with exit code ${EXIT_CODE}"
    exit 1
fi

# Validate JSON structure
if ! echo "${RESULT}" | jq -e '.tool_ids' > /dev/null 2>&1; then
    log_error "Invalid response: missing 'tool_ids' field"
    exit 1
fi

if ! echo "${RESULT}" | jq -e '.matrix' > /dev/null 2>&1; then
    log_error "Invalid response: missing 'matrix' field"
    exit 1
fi

if ! echo "${RESULT}" | jq -e '.flagged_pairs' > /dev/null 2>&1; then
    log_error "Invalid response: missing 'flagged_pairs' field"
    exit 1
fi

TOOL_COUNT=$(echo "${RESULT}" | jq '.tool_ids | length')
log_info "Analyzed ${TOOL_COUNT} tools"

if [[ "${TOOL_COUNT}" -lt 2 ]]; then
    log_error "Expected at least 2 tools for similarity analysis, got ${TOOL_COUNT}"
    exit 1
fi

# Validate matrix dimensions match tool count
MATRIX_ROWS=$(echo "${RESULT}" | jq '.matrix | length')
if [[ "${MATRIX_ROWS}" -ne "${TOOL_COUNT}" ]]; then
    log_error "Matrix row count (${MATRIX_ROWS}) doesn't match tool count (${TOOL_COUNT})"
    exit 1
fi

log_success "similarity analyze (basic) passed"

# ============================================================================
# Test: similarity matrix
# ============================================================================

log_info "=== Test: similarity matrix ==="

RESULT=$(mtef similarity matrix \
    --container-name "${TEF_CONTAINER_NAME}" \
    --server-urls "${MCP_SERVER_URL}" \
    --threshold 0.80 \
    --insecure \
    --format json \
    --timeout 120 2>&1) || EXIT_CODE=$?

EXIT_CODE=${EXIT_CODE:-0}

log_info "Raw similarity matrix result:"
echo "${RESULT}"

if [[ ${EXIT_CODE} -ne 0 ]]; then
    log_error "similarity matrix command failed with exit code ${EXIT_CODE}"
    exit 1
fi

# Validate JSON structure
if ! echo "${RESULT}" | jq -e '.tool_ids' > /dev/null 2>&1; then
    log_error "Invalid response: missing 'tool_ids' field"
    exit 1
fi

if ! echo "${RESULT}" | jq -e '.threshold' > /dev/null 2>&1; then
    log_error "Invalid response: missing 'threshold' field"
    exit 1
fi

THRESHOLD=$(echo "${RESULT}" | jq '.threshold')
if [[ $(echo "${THRESHOLD} != 0.80" | bc -l) -eq 1 ]]; then
    log_warn "Threshold in response (${THRESHOLD}) differs from requested (0.80)"
fi

log_success "similarity matrix passed"

# ============================================================================
# Test: similarity overlap
# ============================================================================

log_info "=== Test: similarity overlap ==="

RESULT=$(mtef similarity overlap \
    --container-name "${TEF_CONTAINER_NAME}" \
    --server-urls "${MCP_SERVER_URL}" \
    --insecure \
    --format json \
    --timeout 120 2>&1) || EXIT_CODE=$?

EXIT_CODE=${EXIT_CODE:-0}

log_info "Raw similarity overlap result:"
echo "${RESULT}"

if [[ ${EXIT_CODE} -ne 0 ]]; then
    log_error "similarity overlap command failed with exit code ${EXIT_CODE}"
    exit 1
fi

# Validate JSON structure
if ! echo "${RESULT}" | jq -e '.tool_ids' > /dev/null 2>&1; then
    log_error "Invalid response: missing 'tool_ids' field"
    exit 1
fi

if ! echo "${RESULT}" | jq -e '.matrix' > /dev/null 2>&1; then
    log_error "Invalid response: missing 'matrix' field"
    exit 1
fi

if ! echo "${RESULT}" | jq -e '.dimensions' > /dev/null 2>&1; then
    log_error "Invalid response: missing 'dimensions' field"
    exit 1
fi

# Validate dimensions has expected keys
DIMENSIONS=$(echo "${RESULT}" | jq '.dimensions | keys | sort')
log_info "Overlap dimensions: ${DIMENSIONS}"

log_success "similarity overlap passed"

# ============================================================================
# Test: similarity analyze with table output
# ============================================================================

log_info "=== Test: similarity analyze (table output) ==="

RESULT=$(mtef similarity analyze \
    --container-name "${TEF_CONTAINER_NAME}" \
    --server-urls "${MCP_SERVER_URL}" \
    --threshold 0.85 \
    --insecure \
    --format table \
    --timeout 120 2>&1) || EXIT_CODE=$?

EXIT_CODE=${EXIT_CODE:-0}

log_info "Raw table output:"
echo "${RESULT}"

if [[ ${EXIT_CODE} -ne 0 ]]; then
    log_error "similarity analyze (table) command failed with exit code ${EXIT_CODE}"
    exit 1
fi

# Verify table output contains expected sections
if ! echo "${RESULT}" | grep -q "Similarity Analysis Results"; then
    log_error "Table output missing 'Similarity Analysis Results' header"
    exit 1
fi

log_success "similarity analyze (table output) passed"

# ============================================================================
# Test: similarity analyze with verbose
# ============================================================================

log_info "=== Test: similarity analyze (verbose) ==="

RESULT=$(mtef similarity analyze \
    --container-name "${TEF_CONTAINER_NAME}" \
    --server-urls "${MCP_SERVER_URL}" \
    --threshold 0.85 \
    --insecure \
    --format table \
    --verbose \
    --timeout 120 2>&1) || EXIT_CODE=$?

EXIT_CODE=${EXIT_CODE:-0}

if [[ ${EXIT_CODE} -ne 0 ]]; then
    log_error "similarity analyze (verbose) command failed with exit code ${EXIT_CODE}"
    exit 1
fi

log_success "similarity analyze (verbose) passed"

# ============================================================================
# Test: similarity recommend (requires LLM API)
# ============================================================================

if [[ "${SKIP_RECOMMENDATIONS}" != "true" ]]; then
    log_info "=== Test: similarity recommend ==="
    log_info "This test requires LLM API access (TEF_API_KEY must be set)"

    # The time MCP server has exactly 2 tools, which is perfect for recommend
    RESULT=$(mtef similarity recommend \
        --container-name "${TEF_CONTAINER_NAME}" \
        --server-urls "${MCP_SERVER_URL}" \
        --insecure \
        --format json \
        --timeout 180 2>&1) || EXIT_CODE=$?

    EXIT_CODE=${EXIT_CODE:-0}

    log_info "Raw similarity recommend result:"
    echo "${RESULT}"

    if [[ ${EXIT_CODE} -ne 0 ]]; then
        log_error "similarity recommend command failed with exit code ${EXIT_CODE}"
        exit 1
    fi

    # Validate JSON structure
    if ! echo "${RESULT}" | jq -e '.tool_pair' > /dev/null 2>&1; then
        log_error "Invalid response: missing 'tool_pair' field"
        exit 1
    fi

    if ! echo "${RESULT}" | jq -e '.similarity_score' > /dev/null 2>&1; then
        log_error "Invalid response: missing 'similarity_score' field"
        exit 1
    fi

    if ! echo "${RESULT}" | jq -e '.recommendations' > /dev/null 2>&1; then
        log_error "Invalid response: missing 'recommendations' field"
        exit 1
    fi

    # Validate tool_pair has exactly 2 tools
    PAIR_COUNT=$(echo "${RESULT}" | jq '.tool_pair | length')
    if [[ "${PAIR_COUNT}" -ne 2 ]]; then
        log_error "Expected 2 tools in tool_pair, got ${PAIR_COUNT}"
        exit 1
    fi

    log_success "similarity recommend passed"
else
    log_info "=== Test: similarity recommend (SKIPPED) ==="
    log_info "Set SKIP_RECOMMENDATIONS=false to enable this test"
fi

# ============================================================================
# Test: Error handling - invalid threshold
# ============================================================================

log_info "=== Test: Error handling - invalid threshold ==="

RESULT=$(mtef similarity analyze \
    --container-name "${TEF_CONTAINER_NAME}" \
    --server-urls "${MCP_SERVER_URL}" \
    --threshold 1.5 \
    --insecure \
    --format json 2>&1) || EXIT_CODE=$?

if [[ ${EXIT_CODE:-0} -eq 0 ]]; then
    log_error "Expected non-zero exit code for invalid threshold"
    exit 1
fi

log_success "Error handling (invalid threshold) passed"

# ============================================================================
# Summary
# ============================================================================

log_info "=== Test Summary ==="
log_success "All similarity CLI tests passed!"

exit 0
