"""Stop command for mcp-tef CLI."""

import click
import docker
from docker.errors import DockerException, NotFound

from mcp_tef_cli.constants import EXIT_DOCKER_NOT_AVAILABLE
from mcp_tef_cli.output import print_error, print_success, print_warning


@click.command()
@click.option(
    "--name",
    default="mcp-tef",
    help="Container name to stop. Default: mcp-tef",
)
@click.option(
    "--remove-image",
    is_flag=True,
    help="Also remove the Docker image after stopping the container.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force stop the container (SIGKILL instead of SIGTERM).",
)
@click.option(
    "--timeout",
    type=int,
    default=10,
    help="Seconds to wait for container to stop before killing. Default: 10",
)
def stop(
    name: str,
    remove_image: bool,
    force: bool,
    timeout: int,
) -> None:
    """Stop and remove a deployed mcp-tef container.

    This command stops a running mcp-tef container and removes it.
    Optionally, it can also remove the Docker image to free up disk space.

    Examples:

      \b
      # Stop the default mcp-tef container
      mtef stop

      \b
      # Stop a named container
      mtef stop --name mcp-tef-dev

      \b
      # Stop container and remove the image
      mtef stop --remove-image

      \b
      # Force stop (immediate kill)
      mtef stop --force
    """
    try:
        client = docker.from_env()
        client.ping()
    except DockerException:
        print_error("Docker daemon not available")
        click.echo("  Ensure Docker is installed and running", err=True)
        raise SystemExit(EXIT_DOCKER_NOT_AVAILABLE)

    # Initialize variables for image tracking (used if --remove-image is set)
    image_id: str | None = None
    image_tags: list[str] = []

    # Find and stop the container
    try:
        container = client.containers.get(name)
        image_id = container.image.id
        image_tags = container.image.tags

        if container.status == "running":
            click.echo(f"Stopping container '{name}'...")
            if force:
                container.kill()
                print_success(f"Container '{name}' killed")
            else:
                container.stop(timeout=timeout)
                print_success(f"Container '{name}' stopped")
        else:
            click.echo(f"Container '{name}' is not running (status: {container.status})")

        # Remove the container
        click.echo(f"Removing container '{name}'...")
        container.remove(force=True)
        print_success(f"Container '{name}' removed")

    except NotFound:
        print_warning(f"Container '{name}' not found")
        if not remove_image:
            return

    # Optionally remove the image
    if remove_image:
        click.echo("")
        try:
            # Try to find mcp-tef images
            images_to_remove: list[tuple[str, list[str]]] = []

            # Check for the specific image used by the container
            if image_id:
                images_to_remove.append((image_id, image_tags))
            else:
                # Find all mcp-tef images
                for img in client.images.list():
                    for tag in img.tags:
                        if "mcp-tef" in tag or "stackloklabs/mcp-tef" in tag:
                            images_to_remove.append((img.id, img.tags))
                            break

            if not images_to_remove:
                print_warning("No mcp-tef images found to remove")
                return

            for img_id, tags in images_to_remove:
                tag_str = tags[0] if tags else img_id[:12]
                click.echo(f"Removing image '{tag_str}'...")
                try:
                    client.images.remove(img_id, force=True)
                    print_success(f"Image '{tag_str}' removed")
                except Exception as e:
                    print_error(f"Failed to remove image '{tag_str}'", str(e))

        except Exception as e:
            print_error("Failed to remove image", str(e))

    # Display summary
    click.echo("")
    print_success("Cleanup complete!")
