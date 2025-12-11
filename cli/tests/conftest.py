"""Pytest configuration and fixtures for CLI tests."""

import docker
import pytest


@pytest.fixture
def docker_client():
    """Docker client fixture.

    Yields:
        Docker client instance

    Raises:
        pytest.skip: If Docker is not available
    """
    try:
        client = docker.from_env()
        # Verify Docker is available
        client.ping()
        yield client
    except docker.errors.DockerException:
        pytest.skip("Docker not available")


@pytest.fixture
def cleanup_container(docker_client):
    """Clean up test containers after each test.

    Yields:
        List to track container names for cleanup

    Cleanup:
        Stops and removes all containers in the list
    """
    container_names = []

    yield container_names

    # Cleanup
    for name in container_names:
        try:
            container = docker_client.containers.get(name)
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            pass
