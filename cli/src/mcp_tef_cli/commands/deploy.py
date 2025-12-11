"""Deploy command for mcp-tef CLI."""

import asyncio

import click
import docker
from docker.errors import NotFound

from mcp_tef_cli.constants import (
    DEFAULT_HEALTH_TIMEOUT,
    DEFAULT_RESTART_MAX_RETRY,
    EXIT_HEALTH_CHECK_FAILED,
    GHCR_IMAGE_BASE,
)
from mcp_tef_cli.docker_client import check_health, deploy_container, parse_env_vars, parse_volumes
from mcp_tef_cli.output import print_error, print_success


def _get_container_logs(container_name: str, tail: int = 50) -> str | None:
    """Get recent logs from a container for troubleshooting.

    Args:
        container_name: Name of the container
        tail: Number of log lines to retrieve

    Returns:
        Log output as string, or None if container not found
    """
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        logs = container.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
        return logs
    except NotFound:
        return None
    except Exception:
        return None


@click.command()
@click.option(
    "--version",
    default="latest",
    help="Image version to pull from GHCR (e.g., v0.2.1, latest). "
    "View available versions at: https://github.com/StacklokLabs/mcp-tef/pkgs/container/mcp-tef",
)
@click.option(
    "--image",
    default=None,
    help="Full image reference (e.g., my-local-image:test). "
    "Overrides --version and pulls from local Docker instead of GHCR. "
    "Useful for testing locally built images.",
)
@click.option("--name", default="mcp-tef", help="Container name")
@click.option(
    "--port", type=int, default=8000, help="Host port to bind (maps to container port 8000)"
)
@click.option(
    "--env",
    multiple=True,
    help="Environment variable in KEY=value format. Can be specified multiple times. "
    "Example: --env OPENROUTER_API_KEY=sk-xxx --env LOG_LEVEL=DEBUG",
)
@click.option(
    "--env-file",
    type=click.Path(exists=True),
    help="Path to .env file with environment variables. "
    "Format: KEY=value (one per line). "
    "Variables specified with --env override values from file.",
)
@click.option(
    "--detach/--no-detach",
    default=True,
    help="Run container in background (detached). Default: --detach",
)
@click.option(
    "--remove",
    is_flag=True,
    default=True,
    help="Remove container on exit (only if --no-detach). Default: True",
)
@click.option(
    "--health-check",
    is_flag=True,
    help="Wait for server health check to pass before returning. "
    "Ensures server is ready before proceeding. "
    "Use --health-timeout to adjust wait time.",
)
@click.option(
    "--health-timeout",
    type=int,
    default=DEFAULT_HEALTH_TIMEOUT,
    help=f"Health check timeout in seconds. Default: {DEFAULT_HEALTH_TIMEOUT}",
)
@click.option(
    "--volume",
    multiple=True,
    help="Volume mount in host:container or host:container:mode format. "
    "Mode can be 'ro' (read-only) or 'rw' (read-write, default). "
    "Can be specified multiple times.",
)
@click.option(
    "--network",
    default=None,
    help="Docker network to attach container to. If not specified, uses default bridge network.",
)
@click.option(
    "--restart",
    type=click.Choice(["no", "always", "on-failure", "unless-stopped"]),
    default="no",
    help="Restart policy for the container. Default: no",
)
@click.option(
    "--restart-max-retry",
    type=int,
    default=DEFAULT_RESTART_MAX_RETRY,
    help=f"Maximum retry count for on-failure restart policy. Default: {DEFAULT_RESTART_MAX_RETRY}",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Skip SSL certificate verification for health checks. "
    "Use this for servers with self-signed certificates.",
)
def deploy(
    version: str,
    image: str | None,
    name: str,
    port: int,
    env: tuple[str, ...],
    env_file: str | None,
    detach: bool,
    remove: bool,
    health_check: bool,
    health_timeout: int,
    volume: tuple[str, ...],
    network: str | None,
    restart: str,
    restart_max_retry: int,
    insecure: bool,
) -> None:
    """Deploy mcp-tef as a Docker container from GitHub Container Registry.

    This command pulls the specified version of mcp-tef from GHCR and runs it
    as a Docker container. The server will be accessible at https://localhost:PORT
    (default: 8000). Note: mcp-tef uses TLS with self-signed certificates by default.

    Examples:

      \b
      # Deploy latest version
      mcp-tef-cli deploy

      \b
      # Deploy specific version with API key
      mcp-tef-cli deploy --version v0.2.1 --env OPENROUTER_API_KEY=sk-xxx

      \b
      # Deploy with environment file and health check
      mcp-tef-cli deploy --env-file .env.prod --health-check

      \b
      # Deploy local test image
      mcp-tef-cli deploy --image my-test-image:dev --port 9000
    """
    try:
        # Parse environment variables
        env_vars = parse_env_vars(list(env), env_file)

        # Parse volume mounts
        volumes = parse_volumes(list(volume))

        # Deploy container
        container = deploy_container(
            version=version,
            image=image,
            name=name,
            port=port,
            env_vars=env_vars,
            detach=detach,
            remove=remove,
            volumes=volumes,
            network=network,
            restart_policy=restart,
            restart_max_retry=restart_max_retry,
        )

        # Health check (mcp-tef uses TLS by default)
        if health_check:
            click.echo("Waiting for server to be ready...")
            success, health_data = asyncio.run(
                check_health(
                    f"https://localhost:{port}",
                    timeout=health_timeout,
                    verify_ssl=not insecure,
                )
            )
            if not success:
                print_error("Health check failed")
                click.echo("\nTroubleshooting: Recent container logs:", err=True)
                click.echo("-" * 40, err=True)
                logs = _get_container_logs(name)
                if logs:
                    click.echo(logs, err=True)
                else:
                    click.echo("  (No logs available)", err=True)
                click.echo("-" * 40, err=True)
                click.echo(f"\nTo view full logs: docker logs {name}", err=True)
                raise SystemExit(EXIT_HEALTH_CHECK_FAILED)

            if health_data:
                print_success(f"Server is healthy: {health_data}")

        # Display deployment summary
        click.echo("\n" + "=" * 60)
        print_success("Deployment complete!")
        click.echo("=" * 60)
        click.echo(f"  Container Name:  {name}")
        click.echo(f"  Container ID:    {container.short_id}")
        click.echo(f"  Image:           {image or f'{GHCR_IMAGE_BASE}:{version}'}")
        click.echo(f"  Port:            {port}")
        click.echo(f"  API:             https://localhost:{port}")
        click.echo(f"  Docs:            https://localhost:{port}/docs")
        if network:
            click.echo(f"  Network:         {network}")
        if restart != "no":
            click.echo(f"  Restart Policy:  {restart}")
        click.echo("=" * 60 + "\n")

    except click.Abort:
        # Already handled by docker_client functions
        raise

    except Exception as e:
        print_error("Deployment failed", str(e))
        raise click.Abort() from e
