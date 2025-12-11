#!/usr/bin/env bash
#
# End-to-end test for query-tool alignment CLI commands using --from-file.
#
# This variant demonstrates creating test cases from a JSON file instead of
# individual CLI arguments.
#
# Prerequisites:
#   - thv (ToolHive CLI) installed and configured
#   - mtef installed (or will be installed from source)
#   - Docker running
#   - TEF_API_KEY or --api-key for LLM provider
#
# Usage:
#   ./test_query_alignment_from_file.sh [--api-key <key>] [--model-provider <provider>] [--model-name <model>]
#

set -euo pipefail

# Source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Default configuration
MODEL_PROVIDER="${MODEL_PROVIDER:-openrouter}"
MODEL_NAME="${MODEL_NAME:-anthropic/claude-sonnet-4.5}"
API_KEY="${TEF_API_KEY:-}"
TEF_CONTAINER_NAME="mcp-tef-query-alignment-test"
TEF_PORT="${TEF_PORT:-8000}"
MCP_SERVER_NAME="fetch"

# Test cases template file (uses ${MCP_SERVER_URL} placeholder)
TEST_CASES_TEMPLATE="${SCRIPT_DIR}/test_cases.json"

# Track created resources for cleanup
TEST_CASE_IDS=()

cleanup() {
    log_info "Cleaning up..."

    # Stop mcp-tef container
    force_remove_mcp_tef "${TEF_CONTAINER_NAME}"

    # Remove MCP server via thv
    remove_mcp_server "${MCP_SERVER_NAME}"

    log_info "Cleanup complete"
}

trap cleanup EXIT

# ============================================================================
# Parse Arguments
# ============================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
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
            log_error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# ============================================================================
# Prerequisite Checks
# ============================================================================

log_info "Checking prerequisites..."

check_docker || exit 1
check_thv || exit 1

# Install mtef from source if not available
if ! check_mcp_tef_cli 2>/dev/null; then
    install_mcp_tef_cli_from_source || exit 1
fi

if [[ -z "${API_KEY}" ]]; then
    log_error "API key required. Set TEF_API_KEY or use --api-key"
    exit 1
fi

log_success "Prerequisites OK"

# ============================================================================
# Test Setup
# ============================================================================

# Step 1: Deploy MCP server using thv
log_info "Step 1: Deploying MCP server '${MCP_SERVER_NAME}'..."
deploy_mcp_server "${MCP_SERVER_NAME}" || exit 1

# Get MCP server URL (rewrite for Docker access)
MCP_SERVER_URL=$(get_mcp_server_url "${MCP_SERVER_NAME}" true)
log_info "MCP server URL: ${MCP_SERVER_URL}"

# Step 2: Build and deploy mcp-tef from source
log_info "Step 2: Building mcp-tef Docker image..."
IMAGE_TAG=$(build_mcp_tef_image) || exit 1
log_success "Built image: ${IMAGE_TAG}"

log_info "Step 3: Deploying mcp-tef container..."
deploy_mcp_tef "${TEF_CONTAINER_NAME}" "${IMAGE_TAG}" \
    --force \
    --port "${TEF_PORT}" \
    --health-check \
    --insecure \
    --detach || exit 1

# ============================================================================
# Test Execution with --from-file
# ============================================================================

# Step 4: Create test cases from template file using --set for variable substitution
log_info "Step 4: Creating test cases from JSON template..."
log_info "Template file: ${TEST_CASES_TEMPLATE}"
log_info "MCP_SERVER_URL: ${MCP_SERVER_URL}"

# Step 5: Create test cases from file (batch import) with --set for variable substitution
# The CLI now supports ${VAR} substitution natively via --set
log_info "Step 5: Creating test cases via --from-file with --set..."
TEST_CASES_OUTPUT=$(mtef test-case create \
    --container-name "${TEF_CONTAINER_NAME}" \
    --from-file "${TEST_CASES_TEMPLATE}" \
    --set "MCP_SERVER_URL=${MCP_SERVER_URL}" \
    --format json \
    --insecure)

# Parse IDs from response (handles both single object and array)
# jq: if array, get all .id; if object, wrap in array first
TEST_CASE_IDS=($(echo "${TEST_CASES_OUTPUT}" | jq -r 'if type == "array" then .[].id else .id end'))
log_success "Created ${#TEST_CASE_IDS[@]} test case(s):"
for tc_id in "${TEST_CASE_IDS[@]}"; do
    log_info "  - ${tc_id}"
done

# Step 6: Verify test cases were created correctly
log_info "Step 6: Verifying test cases retrieved correctly..."
for i in "${!TEST_CASE_IDS[@]}"; do
    tc_id="${TEST_CASE_IDS[$i]}"
    GET_TC_OUTPUT=$(mtef test-case get "${tc_id}" \
        --container-name "${TEF_CONTAINER_NAME}" \
        --format json \
        --insecure)

    GET_TC_NAME=$(echo "${GET_TC_OUTPUT}" | jq -r '.name')
    log_info "Test case ${i}: ${GET_TC_NAME}"
done
log_success "test-case verification: OK"

# Step 7: Verify test case list shows both
log_info "Step 7: Verifying test-case list..."
LIST_TC_OUTPUT=$(mtef test-case list \
    --container-name "${TEF_CONTAINER_NAME}" \
    --format json \
    --insecure)

log_success "test-case list: OK"

# Step 8: Execute test run on first test case (positive test)
log_info "Step 8: Executing test run on first test case..."
FIRST_TC_ID="${TEST_CASE_IDS[0]}"
TEST_RUN_OUTPUT=$(mtef test-run execute "${FIRST_TC_ID}" \
    --container-name "${TEF_CONTAINER_NAME}" \
    --model-provider "${MODEL_PROVIDER}" \
    --model-name "${MODEL_NAME}" \
    --api-key "${API_KEY}" \
    --format json \
    --no-wait \
    --insecure)

TEST_RUN_ID=$(echo "${TEST_RUN_OUTPUT}" | jq -r '.id')
STATUS=$(echo "${TEST_RUN_OUTPUT}" | jq -r '.status')

log_info "Test run ID: ${TEST_RUN_ID}"
log_info "Initial status: ${STATUS}"

# Step 9: Poll until test run completes
POLL_INTERVAL=2
POLL_TIMEOUT=120
POLL_WAITED=0

log_info "Step 9: Polling for completion (timeout: ${POLL_TIMEOUT}s)..."
while [[ "${STATUS}" == "pending" || "${STATUS}" == "running" ]]; do
    if [[ ${POLL_WAITED} -ge ${POLL_TIMEOUT} ]]; then
        log_error "Timeout waiting for test run to complete"
        exit 1
    fi

    sleep ${POLL_INTERVAL}
    POLL_WAITED=$((POLL_WAITED + POLL_INTERVAL))

    POLL_OUTPUT=$(mtef test-run get "${TEST_RUN_ID}" \
        --container-name "${TEF_CONTAINER_NAME}" \
        --format json \
        --insecure)
    STATUS=$(echo "${POLL_OUTPUT}" | jq -r '.status')
    log_info "Status after ${POLL_WAITED}s: ${STATUS}"
done

# Extract final results
CLASSIFICATION=$(echo "${POLL_OUTPUT}" | jq -r '.classification')
log_info "Final status: ${STATUS}"
log_info "Classification: ${CLASSIFICATION}"

# ============================================================================
# Validation
# ============================================================================

# Step 10: Validate results
log_info "Step 10: Validating results..."
if [[ "${STATUS}" != "completed" ]]; then
    log_error "Test run did not complete successfully. Status: ${STATUS}"
    if [[ "${STATUS}" == "failed" ]]; then
        ERROR_MSG=$(echo "${POLL_OUTPUT}" | jq -r '.error_message // "No error message"')
        log_error "Error: ${ERROR_MSG}"
    fi
    exit 1
fi

if [[ "${CLASSIFICATION}" != "TP" ]]; then
    log_warn "Classification is ${CLASSIFICATION}, expected TP"
fi
log_success "Test run validation: OK"

# ============================================================================
# Summary
# ============================================================================

echo ""
log_info "=== Test Summary ==="
log_info "Test Cases Created: ${#TEST_CASE_IDS[@]}"
for i in "${!TEST_CASE_IDS[@]}"; do
    log_info "  Test Case ${i}: ${TEST_CASE_IDS[$i]}"
done
log_info "Test Run ID: ${TEST_RUN_ID}"
log_info "Status: ${STATUS}"
log_info "Classification: ${CLASSIFICATION}"
log_success "All validations passed!"
log_success "--from-file batch import: OK"

exit 0
