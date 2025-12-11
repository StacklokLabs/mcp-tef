"""Docker container management for mcp-tef CLI."""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import click
import docker
import httpx
from docker.errors import APIError, DockerException, ImageNotFound, NotFound

from mcp_tef_cli.constants import (
    DEFAULT_HEALTH_INTERVAL,
    DEFAULT_HEALTH_TIMEOUT,
    DEFAULT_RESTART_MAX_RETRY,
    EXIT_CONTAINER_CREATION_FAILED,
    EXIT_CONTAINER_START_FAILED,
    EXIT_DOCKER_NOT_AVAILABLE,
    EXIT_IMAGE_NOT_FOUND,
    GHCR_IMAGE_BASE,
)
from mcp_tef_cli.output import print_error, print_success, print_warning

if TYPE_CHECKING:
    from docker.models.containers import Container

__all__ = [
    "_is_named_volume",
    "parse_env_vars",
    "parse_volumes",
    "validate_port",
    "deploy_container",
    "check_health",
    "discover_tef_url",
]


def parse_env_vars(env_list: list[str], env_file: str | None) -> dict[str, str]:
    """Parse environment variables from CLI args and .env file.

    Args:
        env_list: List of KEY=value strings from --env
        env_file: Path to .env file from --env-file

    Returns:
        Dictionary of environment variables

    Raises:
        click.BadParameter: Invalid format or file not found
    """
    env_vars = {}

    # Load from .env file
    if env_file:
        env_path = Path(env_file)
        if not env_path.exists():
            raise click.BadParameter(f"File not found: {env_file}")

        with env_path.open() as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" not in line:
                        raise click.BadParameter(
                            f"Invalid format in {env_file} line {line_num}: {line}"
                        )
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()

    # Override with CLI args
    for env_str in env_list:
        if "=" not in env_str:
            raise click.BadParameter(f"Invalid format: {env_str} (expected KEY=value)")
        key, value = env_str.split("=", 1)

        # Validate environment variable name
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
            raise click.BadParameter(
                f"Invalid environment variable name: {key} "
                "(must start with letter or underscore, contain only alphanumeric and underscore)"
            )

        env_vars[key] = value

    return env_vars


def _is_named_volume(path: str) -> bool:
    """Check if a path looks like a Docker named volume.

    Named volumes are simple identifiers without path separators.
    They must start with a letter or underscore and contain only alphanumeric,
    underscores, and hyphens.

    Args:
        path: The path string to check

    Returns:
        True if the path looks like a named volume, False otherwise
    """
    # Named volumes don't contain path separators and aren't relative paths
    if "/" in path or "\\" in path:
        return False
    # Named volumes start with alphanumeric or underscore
    if not path or not (path[0].isalnum() or path[0] == "_"):
        return False
    # Named volumes contain only alphanumeric, underscores, and hyphens
    return all(c.isalnum() or c in "_-" for c in path)


def parse_volumes(volume_list: list[str]) -> dict[str, dict[str, str]]:
    """Parse volume mounts from CLI args.

    Args:
        volume_list: List of volume mount strings (host:container or host:container:mode)

    Returns:
        Dictionary of volume mounts for Docker SDK

    Raises:
        click.BadParameter: Invalid volume format or host path doesn't exist
    """
    volumes = {}

    for volume_str in volume_list:
        parts = volume_str.split(":")
        if len(parts) < 2 or len(parts) > 3:
            raise click.BadParameter(
                f"Invalid volume format: {volume_str} "
                "(expected host:container or host:container:mode)"
            )

        host_path = parts[0]
        container_path = parts[1]
        mode = parts[2] if len(parts) == 3 else "rw"

        # Validate mode
        if mode not in ["ro", "rw"]:
            raise click.BadParameter(f"Invalid volume mode: {mode} (must be 'ro' or 'rw')")

        # Check if host path exists
        # Skip validation for named volumes (e.g., "myvolume:/container/path")
        if _is_named_volume(host_path):
            # Named volume - Docker will create it if needed
            pass
        else:
            # File system path - resolve and validate
            resolved_path = Path(host_path).resolve()
            if not resolved_path.exists():
                raise click.BadParameter(
                    f"Host path '{host_path}' does not exist. "
                    "Create the directory first: mkdir -p {host_path}"
                )

        volumes[host_path] = {"bind": container_path, "mode": mode}

    return volumes


def validate_port(port: int) -> None:
    """Validate port number.

    Args:
        port: Port number to validate

    Raises:
        click.BadParameter: Invalid port number
    """
    if not 1 <= port <= 65535:
        raise click.BadParameter(f"Port must be between 1 and 65535, got {port}")


def deploy_container(
    version: str = "latest",
    image: str | None = None,
    name: str = "mcp-tef",
    port: int = 8000,
    env_vars: dict[str, str] | None = None,
    detach: bool = True,
    remove: bool = True,
    volumes: dict[str, dict[str, str]] | None = None,
    network: str | None = None,
    restart_policy: str = "no",
    restart_max_retry: int = DEFAULT_RESTART_MAX_RETRY,
) -> Container:
    """Deploy mcp-tef container from GHCR or custom image.

    Args:
        version: Image tag to pull from GHCR (ignored if image is provided)
        image: Full image reference (e.g., 'my-local-image:test'), overrides GHCR default
        name: Container name
        port: Host port to bind
        env_vars: Environment variables
        detach: Run in background
        remove: Remove container on exit
        volumes: Volume mounts
        network: Docker network
        restart_policy: Restart policy (no, always, on-failure, unless-stopped)
        restart_max_retry: Maximum retry count for on-failure restart policy

    Returns:
        Container instance

    Raises:
        DockerException: Docker daemon not available
        ImageNotFound: Image not found
        APIError: Container creation/start failed
    """
    # Validate port
    validate_port(port)

    try:
        client = docker.from_env()
        client.ping()  # Verify Docker is available
    except DockerException:
        print_error("Docker daemon not available")
        click.echo("  Ensure Docker is installed and running", err=True)
        raise SystemExit(EXIT_DOCKER_NOT_AVAILABLE)

    # Determine image reference
    if image:
        # Custom image provided (e.g., local testing image)
        image_ref = image
        click.echo(f"Using custom image: {image_ref}")
    else:
        # Default to GHCR with specified version
        image_ref = f"{GHCR_IMAGE_BASE}:{version}"
        click.echo(f"Pulling image {image_ref}...")

    # Pull image (only if not using custom local image)
    if not image:
        try:
            image_obj = client.images.pull(GHCR_IMAGE_BASE, tag=version)
            if image_obj.tags:
                print_success(f"Pulled {image_obj.tags[0]}")
            else:
                print_success(f"Pulled {image_ref}")
        except ImageNotFound:
            print_error(f"Image not found: {image_ref}")
            click.echo(
                "  Available versions: https://github.com/StacklokLabs/mcp-tef/pkgs/container/mcp-tef",
                err=True,
            )
            raise SystemExit(EXIT_IMAGE_NOT_FOUND)
    else:
        # Verify local image exists
        try:
            client.images.get(image_ref)
            print_success(f"Local image found: {image_ref}")
        except ImageNotFound:
            print_error(f"Local image not found: {image_ref}")
            click.echo(f"  Build the image first with: docker build -t {image_ref} .", err=True)
            raise SystemExit(EXIT_IMAGE_NOT_FOUND)

    # Stop and remove existing container with same name
    try:
        existing = client.containers.get(name)
        print_warning(
            f"Container '{name}' already exists (status: {existing.status}). "
            "It will be stopped and replaced."
        )
        click.echo(f"Stopping existing container '{name}'...")
        existing.stop()
        existing.remove()
        print_success(f"Existing container '{name}' removed")
    except NotFound:
        pass

    # Prepare restart policy
    restart_policy_dict: dict[str, str | int] = {"Name": restart_policy}
    if restart_policy == "on-failure":
        restart_policy_dict["MaximumRetryCount"] = restart_max_retry

    # Run container
    click.echo(f"Starting container '{name}' on port {port}...")
    try:
        container = client.containers.run(
            image=image_ref,
            name=name,
            detach=detach,
            remove=remove if not detach else False,  # Don't auto-remove detached containers
            ports={"8000/tcp": port},
            environment=env_vars or {},
            volumes=volumes or {},
            network=network,
            restart_policy=restart_policy_dict,
        )
    except APIError as e:
        # Distinguish between creation and start failures
        error_msg = str(e).lower()
        if "conflict" in error_msg or "already" in error_msg:
            print_error(f"Container creation failed: {e}")
            raise SystemExit(EXIT_CONTAINER_CREATION_FAILED)
        elif "start" in error_msg or "run" in error_msg:
            print_error(f"Container start failed: {e}")
            raise SystemExit(EXIT_CONTAINER_START_FAILED)
        else:
            print_error(f"Container creation failed: {e}")
            raise SystemExit(EXIT_CONTAINER_CREATION_FAILED)

    print_success(f"Container '{name}' started (ID: {container.short_id})")
    click.echo(f"  API: https://localhost:{port}")
    click.echo(f"  Docs: https://localhost:{port}/docs")

    return container


def discover_tef_url(container_name: str = "mcp-tef") -> str:
    """Discover the mcp-tef server URL from a running Docker container.

    Searches for a running mcp-tef container and extracts the host port
    from its port mappings.

    Args:
        container_name: Name of the container to look for (default: "mcp-tef")

    Returns:
        The mcp-tef URL (e.g., "https://localhost:8000")

    Raises:
        click.ClickException: If Docker is not available, container not found,
            container not running, or port mapping not found
    """
    try:
        client = docker.from_env()
    except DockerException as e:
        raise click.ClickException(f"Docker daemon not available: {e}") from e

    try:
        container = client.containers.get(container_name)
    except NotFound as e:
        raise click.ClickException(
            f"Container '{container_name}' not found. Deploy mcp-tef first with: mcp-tef-cli deploy"
        ) from e

    if container.status != "running":
        raise click.ClickException(
            f"Container '{container_name}' is not running (status: {container.status}). "
            f"Start it with: docker start {container_name}"
        )

    # Get port mappings
    ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
    tcp_port = ports.get("8000/tcp")
    if not tcp_port:
        raise click.ClickException(f"Container '{container_name}' has no port mapping for 8000/tcp")

    host_port = tcp_port[0].get("HostPort")
    if not host_port:
        raise click.ClickException(f"Container '{container_name}' port mapping missing HostPort")

    return f"https://localhost:{host_port}"


async def check_health(
    base_url: str,
    timeout: int = DEFAULT_HEALTH_TIMEOUT,
    interval: int = DEFAULT_HEALTH_INTERVAL,
    verify_ssl: bool = True,
) -> tuple[bool, dict | None]:
    """Poll /health endpoint until server is ready.

    Args:
        base_url: Server base URL (e.g., https://localhost:8000)
        timeout: Maximum wait time in seconds
        interval: Polling interval in seconds
        verify_ssl: Whether to verify SSL certificates (set False for self-signed certs)

    Returns:
        Tuple of (success, health_data)
    """
    health_url = f"{base_url}/health"
    start_time = time.monotonic()

    async with httpx.AsyncClient(verify=verify_ssl) as client:
        while (time.monotonic() - start_time) < timeout:
            try:
                response = await client.get(health_url, timeout=5.0)
                if response.status_code == 200:
                    print_success("Health check passed")
                    return True, response.json()
            except (httpx.ConnectError, httpx.TimeoutException):
                pass

            await asyncio.sleep(interval)

    print_error("Health check timeout")
    return False, None
