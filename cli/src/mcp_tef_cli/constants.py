"""Constants for mcp-tef CLI.

This module contains shared constants used across the CLI, including exit codes
defined in the CLI specification (https://github.com/StacklokLabs/mcp-tef/issues/100).
"""

# Exit codes per spec (https://github.com/StacklokLabs/mcp-tef/issues/100)
EXIT_SUCCESS = 0
EXIT_DOCKER_NOT_AVAILABLE = 1
EXIT_IMAGE_NOT_FOUND = 2
EXIT_CONTAINER_CREATION_FAILED = 3
EXIT_CONTAINER_START_FAILED = 4
EXIT_HEALTH_CHECK_FAILED = 5
EXIT_INVALID_ARGUMENTS = 10
EXIT_TEF_SERVER_UNREACHABLE = 11
EXIT_REQUEST_TIMEOUT = 12
EXIT_RESOURCE_NOT_FOUND = 13

# Default configuration values
DEFAULT_CONTAINER_NAME = "mcp-tef"
DEFAULT_PORT = 8000
DEFAULT_HEALTH_TIMEOUT = 30
DEFAULT_HEALTH_INTERVAL = 2
DEFAULT_STOP_TIMEOUT = 10
DEFAULT_RESTART_MAX_RETRY = 5

# GHCR image reference
GHCR_IMAGE_BASE = "ghcr.io/stackloklabs/mcp-tef"
