"""Shared utility functions for mcp-tef CLI commands."""

from collections.abc import Generator
from contextlib import contextmanager

import httpx

from mcp_tef_cli.constants import (
    DEFAULT_CONTAINER_NAME,
    EXIT_REQUEST_TIMEOUT,
    EXIT_RESOURCE_NOT_FOUND,
    EXIT_TEF_SERVER_UNREACHABLE,
)
from mcp_tef_cli.docker_client import discover_tef_url
from mcp_tef_cli.output import print_error, print_info


@contextmanager
def handle_api_errors(
    url: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> Generator[None]:
    """Context manager for handling common API errors.

    Handles TimeoutException, TimeoutError, ConnectError, and HTTPStatusError
    with appropriate error messages and exit codes.

    Args:
        url: The mcp-tef server URL (for error messages)
        resource_type: Type of resource being accessed (e.g., "Test case", "Test run")
        resource_id: ID of the resource (for 404 error messages)

    Yields:
        None

    Raises:
        SystemExit: With appropriate exit code on error
    """
    try:
        yield
    except TimeoutError as e:
        # Polling timeout (asyncio.wait_for)
        print_error("Polling timed out", str(e) if str(e) else None)
        raise SystemExit(EXIT_REQUEST_TIMEOUT) from e
    except httpx.TimeoutException as e:
        print_error("Request timed out")
        raise SystemExit(EXIT_REQUEST_TIMEOUT) from e
    except httpx.ConnectError as e:
        print_error("Cannot connect to mcp-tef server", f"URL: {url}")
        raise SystemExit(EXIT_TEF_SERVER_UNREACHABLE) from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404 and resource_type and resource_id:
            print_error(f"{resource_type} not found", f"ID: {resource_id}")
            raise SystemExit(EXIT_RESOURCE_NOT_FOUND) from e
        print_error(
            "HTTP error from mcp-tef server",
            f"Status: {e.response.status_code} - {e.response.text}",
        )
        raise SystemExit(EXIT_TEF_SERVER_UNREACHABLE) from e


def resolve_tef_url(
    tef_url: str | None,
    container_name: str | None,
    output_format: str,
) -> str:
    """Resolve mcp-tef URL from CLI arg or Docker discovery.

    Args:
        tef_url: Explicit URL from CLI
        container_name: Container name for discovery
        output_format: Output format (suppress info for json)

    Returns:
        Resolved URL
    """
    if tef_url:
        if output_format != "json":
            print_info(f"Using mcp-tef at {tef_url}")
        return tef_url

    url = discover_tef_url(container_name or DEFAULT_CONTAINER_NAME)
    if output_format != "json":
        print_info(f"Discovered mcp-tef at {url}")
    return url
