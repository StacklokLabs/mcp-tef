#!/usr/bin/env bash
#
# Common functions for mcp-tef CLI end-to-end tests.
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
#

# Prevent double-sourcing
if [[ -n "${_COMMON_SH_LOADED:-}" ]]; then
    return 0
fi
_COMMON_SH_LOADED=1

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# Logging Functions
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

# ============================================================================
# Prerequisite Checks
# ============================================================================

# Check that Docker is installed and running
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        return 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        return 1
    fi

    return 0
}

# Check that uv is installed
check_uv() {
    if ! command -v uv &> /dev/null; then
        log_error "uv is not installed"
        return 1
    fi

    return 0
}

# Check that thv (ToolHive CLI) is installed
check_thv() {
    if ! command -v thv &> /dev/null; then
        log_error "thv (ToolHive CLI) not found. Install from: https://github.com/stacklok/toolhive"
        return 1
    fi

    return 0
}

# Check that mtef is installed
check_mcp_tef_cli() {
    if ! command -v mtef &> /dev/null; then
        log_error "mtef not found. Install with: uv tool install mcp-tef-cli"
        return 1
    fi

    return 0
}

# ============================================================================
# CLI Installation
# ============================================================================

# Install mtef from source
# Usage: install_mcp_tef_cli_from_source
install_mcp_tef_cli_from_source() {
    local cli_dir
    cli_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

    log_info "Installing mtef from source: ${cli_dir}"

    if ! check_uv; then
        return 1
    fi

    (cd "$cli_dir" && uv tool install --editable . --force)

    if ! command -v mtef &> /dev/null; then
        log_error "mtef not found in PATH after installation"
        return 1
    fi

    log_success "mtef installed: $(mtef --version)"
    return 0
}

# ============================================================================
# Docker Image Building
# ============================================================================

# Default local image name for testing
MCP_TEF_LOCAL_IMAGE="${MCP_TEF_LOCAL_IMAGE:-mcp-tef-local:dev}"

# Build mcp-tef Docker image from source
# Usage: build_mcp_tef_image [image_tag]
# Args:
#   image_tag - Optional. Tag for the built image. Defaults to MCP_TEF_LOCAL_IMAGE.
# Returns: 0 on success, 1 on failure
# Outputs: The image tag to stdout on success
build_mcp_tef_image() {
    local image_tag="${1:-$MCP_TEF_LOCAL_IMAGE}"

    # Find the repository root (where Dockerfile is)
    local repo_root
    repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

    if [[ ! -f "${repo_root}/Dockerfile" ]]; then
        log_error "Dockerfile not found at ${repo_root}/Dockerfile"
        return 1
    fi

    if ! docker build -t "${image_tag}" "${repo_root}" > /dev/null; then
        log_error "Failed to build Docker image: ${image_tag}"
        return 1
    fi

    echo "${image_tag}"
    return 0
}

# ============================================================================
# mcp-tef Container Management
# ============================================================================

# Check if mcp-tef container is deployed and running
# Usage: is_mcp_tef_deployed <container_name>
# Returns: 0 if running, 1 otherwise
is_mcp_tef_deployed() {
    local container_name="$1"

    if [[ -z "$container_name" ]]; then
        log_error "Container name required"
        return 1
    fi

    local status
    status=$(docker inspect -f '{{.State.Status}}' "$container_name" 2>/dev/null || echo "not_found")

    if [[ "$status" == "running" ]]; then
        return 0
    fi

    return 1
}

# Deploy mcp-tef container using CLI
# Usage: deploy_mcp_tef <container_name> [image] [additional_args...]
# Args:
#   container_name - Required. Name for the container.
#   image - Optional. Docker image to use (e.g., "mcp-tef-local:dev").
#           If empty or "-", uses CLI default.
#   --force - Force redeployment even if container is already running.
# Example: deploy_mcp_tef "my-container" "mcp-tef-local:dev" --port 8080
# Example: deploy_mcp_tef "my-container" "" --port 8080  # uses default image
# Example: deploy_mcp_tef "my-container" "mcp-tef-local:dev" --force --port 8080
deploy_mcp_tef() {
    local container_name="$1"
    local image="${2:-}"
    shift 2 2>/dev/null || shift 1 2>/dev/null || true

    # Parse --force flag from remaining args
    local force=false
    local extra_args=()
    for arg in "$@"; do
        if [[ "$arg" == "--force" ]]; then
            force=true
        else
            extra_args+=("$arg")
        fi
    done

    if [[ -z "$container_name" ]]; then
        log_error "Container name required"
        return 1
    fi

    # Check if already deployed
    if is_mcp_tef_deployed "$container_name"; then
        if [[ "$force" == "true" ]]; then
            log_info "Force flag set, removing existing container '${container_name}'"
        else
            log_info "mcp-tef container '${container_name}' is already running, skipping deployment"
            return 0
        fi
    fi

    log_info "Deploying mcp-tef container: ${container_name}"

    # Remove any existing container with the same name (running or stopped)
    docker rm -f "$container_name" 2>/dev/null || true

    # Build command arguments
    local cmd_args=(--name "$container_name")
    if [[ -n "$image" && "$image" != "-" ]]; then
        cmd_args+=(--image "$image")
    fi
    cmd_args+=("${extra_args[@]}")

    # Deploy using CLI
    mtef deploy "${cmd_args[@]}"

    # Verify deployment
    if ! is_mcp_tef_deployed "$container_name"; then
        log_error "Failed to deploy mcp-tef container '${container_name}'"
        docker logs "$container_name" 2>/dev/null || true
        return 1
    fi

    log_success "mcp-tef container '${container_name}' deployed successfully"
    return 0
}

# Stop mcp-tef container using CLI
# Usage: stop_mcp_tef <container_name>
stop_mcp_tef() {
    local container_name="$1"

    if [[ -z "$container_name" ]]; then
        log_error "Container name required"
        return 1
    fi

    log_info "Stopping mcp-tef container: ${container_name}"

    mtef stop --name "$container_name"

    # Verify container is removed
    if docker inspect "$container_name" &> /dev/null; then
        log_error "Container '${container_name}' still exists after stop"
        return 1
    fi

    log_success "mcp-tef container '${container_name}' stopped and removed"
    return 0
}

# Force remove mcp-tef container using docker rm (last-resort cleanup)
# Usage: force_remove_mcp_tef <container_name>
force_remove_mcp_tef() {
    local container_name="$1"

    if [[ -z "$container_name" ]]; then
        log_error "Container name required"
        return 1
    fi

    # Check if container exists
    if ! docker inspect "$container_name" &> /dev/null; then
        log_info "Container '${container_name}' does not exist, nothing to remove"
        return 0
    fi

    log_info "Force removing container: ${container_name}"
    docker rm -f "$container_name" 2>/dev/null || true

    log_success "Container '${container_name}' removed"
    return 0
}

# ============================================================================
# MCP Server Management (via thv)
# ============================================================================

# Check if MCP server is deployed and running via thv
# Usage: is_mcp_server_deployed <name>
# Returns: 0 if running, 1 otherwise
is_mcp_server_deployed() {
    local name="$1"

    if [[ -z "$name" ]]; then
        log_error "MCP server name required"
        return 1
    fi

    if thv list --format json 2>/dev/null | jq -e ".[] | select(.name == \"${name}\" and .status == \"running\")" > /dev/null 2>&1; then
        return 0
    fi

    return 1
}

# Deploy MCP server using thv and poll for running status
# Usage: deploy_mcp_server <name> [timeout_seconds]
# Default timeout: 30 seconds
deploy_mcp_server() {
    local name="$1"
    local timeout="${2:-30}"

    if [[ -z "$name" ]]; then
        log_error "MCP server name required"
        return 1
    fi

    # Check if already running
    if is_mcp_server_deployed "$name"; then
        log_info "MCP server '${name}' is already running, skipping deployment"
        return 0
    fi

    log_info "Deploying MCP server: ${name}"
    thv run "$name"

    # Poll for server to be running
    log_info "Waiting for '${name}' to be ready (timeout: ${timeout}s)..."
    local waited=0
    local interval=1

    while [[ ${waited} -lt ${timeout} ]]; do
        if is_mcp_server_deployed "$name"; then
            log_success "MCP server '${name}' is running"
            return 0
        fi
        sleep ${interval}
        waited=$((waited + interval))
    done

    log_error "Timeout waiting for MCP server '${name}' to be ready"
    return 1
}

# Remove MCP server using thv
# Usage: remove_mcp_server <name>
remove_mcp_server() {
    local name="$1"

    if [[ -z "$name" ]]; then
        log_error "MCP server name required"
        return 1
    fi

    # Check if server exists
    if ! thv list --format json 2>/dev/null | jq -e ".[] | select(.name == \"${name}\")" > /dev/null 2>&1; then
        log_info "MCP server '${name}' does not exist, nothing to remove"
        return 0
    fi

    log_info "Removing MCP server: ${name}"
    thv rm "$name"

    log_success "MCP server '${name}' removed"
    return 0
}

# Get MCP server URL from thv list
# Usage: get_mcp_server_url <name> [docker_host_rewrite]
# If docker_host_rewrite is "true", rewrites 127.0.0.1 to host.docker.internal
get_mcp_server_url() {
    local name="$1"
    local docker_host_rewrite="${2:-false}"

    if [[ -z "$name" ]]; then
        log_error "MCP server name required"
        return 1
    fi

    local url
    url=$(thv list --format json | jq -r ".[] | select(.name == \"${name}\") | .url")

    if [[ -z "$url" || "$url" == "null" ]]; then
        log_error "Failed to get URL for MCP server '${name}'"
        return 1
    fi

    if [[ "$docker_host_rewrite" == "true" ]]; then
        url=$(echo "$url" | sed "s/127\.0\.0\.1/host.docker.internal/g")
    fi

    echo "$url"
    return 0
}
