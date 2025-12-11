#!/usr/bin/env bash
#
# End-to-end test for mcp-tef-cli deploy and stop commands.
# This script installs the CLI from source and validates basic functionality.
#

set -euo pipefail

# Source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Test configuration
CONTAINER_NAME="test-mcp-tef-e2e"
TEST_PORT=8099
LOCAL_IMAGE=""  # Will be set after building

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    force_remove_mcp_tef "$CONTAINER_NAME"
    log_info "Cleanup complete"
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Check prerequisites
log_info "Checking prerequisites..."

if ! check_docker; then
    exit 1
fi

if ! check_uv; then
    exit 1
fi

log_success "Prerequisites OK"

# Step 1: Build local Docker image
log_info "Step 1: Building local Docker image..."

LOCAL_IMAGE=$(build_mcp_tef_image) || exit 1

# Step 2: Install CLI from source
log_info "Step 2: Installing mcp-tef-cli from source..."

if ! install_mcp_tef_cli_from_source; then
    exit 1
fi

# Step 3: Deploy container
log_info "Step 3: Deploying mcp-tef container..."

if ! deploy_mcp_tef "$CONTAINER_NAME" "$LOCAL_IMAGE" --force --port "$TEST_PORT"; then
    exit 1
fi

# Step 4: Validate container is running
log_info "Step 4: Validating container is running..."

if is_mcp_tef_deployed "$CONTAINER_NAME"; then
    log_success "Container '$CONTAINER_NAME' is running"
else
    log_error "Container '$CONTAINER_NAME' is not running"
    docker logs "$CONTAINER_NAME" 2>/dev/null || true
    exit 1
fi

# Verify port mapping
PORT_MAPPING=$(docker port "$CONTAINER_NAME" 8000 2>/dev/null || echo "")
if [[ -n "$PORT_MAPPING" ]]; then
    log_success "Port mapping: 8000/tcp -> $PORT_MAPPING"
else
    log_error "Port mapping not found"
    exit 1
fi

# Step 5: Stop container using CLI
log_info "Step 5: Stopping container with CLI..."

if ! stop_mcp_tef "$CONTAINER_NAME"; then
    exit 1
fi

# Step 6: Validate container is removed
log_info "Step 6: Validating container is removed..."

if docker inspect "$CONTAINER_NAME" &> /dev/null; then
    log_error "Container '$CONTAINER_NAME' still exists after stop"
    exit 1
else
    log_success "Container '$CONTAINER_NAME' successfully removed"
fi

# All tests passed
log_success "All tests passed!"
