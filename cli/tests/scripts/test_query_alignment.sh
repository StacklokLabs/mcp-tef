#!/usr/bin/env bash
#
# End-to-end test for query-tool alignment CLI commands.
#
# Prerequisites:
#   - thv (ToolHive CLI) installed and configured
#   - mcp-tef-cli installed (or will be installed from source)
#   - Docker running
#   - TEF_API_KEY or --api-key for LLM provider
#
# Usage:
#   ./test_query_alignment.sh [--api-key <key>] [--model-provider <provider>] [--model-name <model>]
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

# Track created resources for cleanup
TEST_CASE_ID=""

cleanup() {
    log_info "Cleaning up..."

    # Delete test case if created
    if [[ -n "${TEST_CASE_ID}" ]]; then
        mcp-tef-cli test-case delete "${TEST_CASE_ID}" \
            --container-name "${TEF_CONTAINER_NAME}" \
            --yes --insecure 2>/dev/null || true
    fi

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

# Install mcp-tef-cli from source if not available
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
# Test Execution
# ============================================================================

# Step 4: Create test case
log_info "Step 4: Creating test case..."
TEST_CASE_OUTPUT=$(mcp-tef-cli test-case create \
    --container-name "${TEF_CONTAINER_NAME}" \
    --name "E2E Fetch Test" \
    --query "Fetch the content from https://example.com" \
    --expected-server "${MCP_SERVER_URL}" \
    --expected-tool "fetch" \
    --servers "${MCP_SERVER_URL}" \
    --format json \
    --insecure)

TEST_CASE_ID=$(echo "${TEST_CASE_OUTPUT}" | jq -r '.id')
log_success "Created test case: ${TEST_CASE_ID}"

# Step 5: Verify test case retrieval
log_info "Step 5: Verifying test-case get..."
GET_TC_OUTPUT=$(mcp-tef-cli test-case get "${TEST_CASE_ID}" \
    --container-name "${TEF_CONTAINER_NAME}" \
    --format json \
    --insecure)

GET_TC_NAME=$(echo "${GET_TC_OUTPUT}" | jq -r '.name')
if [[ "${GET_TC_NAME}" != "E2E Fetch Test" ]]; then
    log_error "Test case name mismatch: expected 'E2E Fetch Test', got '${GET_TC_NAME}'"
    exit 1
fi
log_success "test-case get: OK"

# Step 6: Verify test case list
log_info "Step 6: Verifying test-case list..."
LIST_TC_OUTPUT=$(mcp-tef-cli test-case list \
    --container-name "${TEF_CONTAINER_NAME}" \
    --format json \
    --insecure)

LIST_TC_COUNT=$(echo "${LIST_TC_OUTPUT}" | jq '.total')
if [[ "${LIST_TC_COUNT}" -lt 1 ]]; then
    log_error "Expected at least 1 test case in list"
    exit 1
fi
log_success "test-case list: OK (${LIST_TC_COUNT} total)"

# Step 7: Execute test run (with --no-wait to demonstrate polling)
log_info "Step 7: Executing test run..."
TEST_RUN_OUTPUT=$(mcp-tef-cli test-run execute "${TEST_CASE_ID}" \
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

# Step 8: Poll until test run completes
POLL_INTERVAL=2
POLL_TIMEOUT=120
POLL_WAITED=0

log_info "Step 8: Polling for completion (timeout: ${POLL_TIMEOUT}s)..."
while [[ "${STATUS}" == "pending" || "${STATUS}" == "running" ]]; do
    if [[ ${POLL_WAITED} -ge ${POLL_TIMEOUT} ]]; then
        log_error "Timeout waiting for test run to complete"
        exit 1
    fi

    sleep ${POLL_INTERVAL}
    POLL_WAITED=$((POLL_WAITED + POLL_INTERVAL))

    POLL_OUTPUT=$(mcp-tef-cli test-run get "${TEST_RUN_ID}" \
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

# Step 9: Validate results
log_info "Step 9: Validating results..."
if [[ "${STATUS}" != "completed" ]]; then
    log_error "Test run did not complete successfully. Status: ${STATUS}"
    # Show error details if failed
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

# Step 10: Verify test-run get
log_info "Step 10: Verifying test-run get..."
GET_OUTPUT=$(mcp-tef-cli test-run get "${TEST_RUN_ID}" \
    --container-name "${TEF_CONTAINER_NAME}" \
    --format json \
    --insecure)

GET_STATUS=$(echo "${GET_OUTPUT}" | jq -r '.status')
if [[ "${GET_STATUS}" != "${STATUS}" ]]; then
    log_error "Status mismatch: expected ${STATUS}, got ${GET_STATUS}"
    exit 1
fi
log_success "test-run get: OK"

# Step 11: Verify test-run list
log_info "Step 11: Verifying test-run list..."
LIST_OUTPUT=$(mcp-tef-cli test-run list \
    --container-name "${TEF_CONTAINER_NAME}" \
    --test-case-id "${TEST_CASE_ID}" \
    --format json \
    --insecure)

LIST_COUNT=$(echo "${LIST_OUTPUT}" | jq '.count')
if [[ "${LIST_COUNT}" -lt 1 ]]; then
    log_error "Expected at least 1 test run in list"
    exit 1
fi
log_success "test-run list: OK"

# ============================================================================
# Summary
# ============================================================================

echo ""
log_info "=== Test Summary ==="
log_info "Test Case ID: ${TEST_CASE_ID}"
log_info "Test Run ID: ${TEST_RUN_ID}"
log_info "Status: ${STATUS}"
log_info "Classification: ${CLASSIFICATION}"
log_success "All validations passed!"

exit 0
