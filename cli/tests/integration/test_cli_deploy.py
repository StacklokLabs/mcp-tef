"""Integration tests for CLI deployment functionality."""

import docker
import pytest

from mcp_tef_cli.client import ClientConfig, TefClient
from mcp_tef_cli.constants import DEFAULT_HEALTH_TIMEOUT
from mcp_tef_cli.docker_client import (
    check_health,
    deploy_container,
    parse_env_vars,
    parse_volumes,
)

# Health check timeout for tests (longer than default to account for slow container startup)
TEST_HEALTH_TIMEOUT = DEFAULT_HEALTH_TIMEOUT + 30

pytestmark = [pytest.mark.integration, pytest.mark.docker]


class TestEnvVarParsing:
    """Test environment variable parsing."""

    def test_parse_env_vars_from_list(self):
        """Test parsing environment variables from list."""
        env_list = ["KEY1=value1", "KEY2=value2", "KEY3=value with spaces"]
        env_vars = parse_env_vars(env_list, None)

        assert env_vars == {"KEY1": "value1", "KEY2": "value2", "KEY3": "value with spaces"}

    def test_parse_env_vars_from_file(self, tmp_path):
        """Test parsing environment variables from file."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n# Comment\nKEY3=value3\n")

        env_vars = parse_env_vars([], str(env_file))

        assert env_vars == {"KEY1": "value1", "KEY2": "value2", "KEY3": "value3"}

    def test_parse_env_vars_override(self, tmp_path):
        """Test that CLI args override file values."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=file_value\nKEY2=value2\n")

        env_list = ["KEY1=cli_value"]
        env_vars = parse_env_vars(env_list, str(env_file))

        assert env_vars == {"KEY1": "cli_value", "KEY2": "value2"}

    def test_parse_env_vars_invalid_format(self):
        """Test error on invalid format."""
        import click

        with pytest.raises(click.BadParameter, match="Invalid format"):
            parse_env_vars(["INVALID"], None)

    def test_parse_env_vars_invalid_key_name(self):
        """Test error on invalid key name."""
        import click

        with pytest.raises(click.BadParameter, match="Invalid environment variable name"):
            parse_env_vars(["123-INVALID=value"], None)


class TestVolumeParsing:
    """Test volume mount parsing."""

    def test_parse_volumes_basic(self, tmp_path):
        """Test basic volume mount parsing."""
        host_path = tmp_path / "host"
        host_path.mkdir()
        volume_list = [f"{host_path}:/container/path"]
        volumes = parse_volumes(volume_list)

        assert volumes == {str(host_path): {"bind": "/container/path", "mode": "rw"}}

    def test_parse_volumes_with_mode(self, tmp_path):
        """Test volume mount with explicit mode."""
        host_path = tmp_path / "host"
        host_path.mkdir()
        volume_list = [f"{host_path}:/container/path:ro"]
        volumes = parse_volumes(volume_list)

        assert volumes == {str(host_path): {"bind": "/container/path", "mode": "ro"}}

    def test_parse_volumes_invalid_format(self):
        """Test error on invalid format."""
        import click

        with pytest.raises(click.BadParameter, match="Invalid volume format"):
            parse_volumes(["invalid"])

    def test_parse_volumes_invalid_mode(self):
        """Test error on invalid mode."""
        import click

        with pytest.raises(click.BadParameter, match="Invalid volume mode"):
            parse_volumes(["/host:/container:invalid"])


class TestDockerDeployment:
    """Test Docker container deployment.

    Note: These tests require:
    1. Docker daemon running
    2. Access to GHCR or a locally built image (ghcr.io/stackloklabs/mcp-tef:latest)
    3. Available ports for testing (8001-8006)

    To run these tests:
    1. Pull image: docker pull ghcr.io/stackloklabs/mcp-tef:latest
    2. Run: pytest tests/integration/test_cli_deploy.py::TestDockerDeployment -v
    """

    @pytest.mark.asyncio
    async def test_deploy_pull_latest(self, docker_client, cleanup_container):
        """Test deploying latest image from GHCR."""
        container_name = "test-mcp-tef-pull"
        cleanup_container.append(container_name)

        # Deploy container (default pulls from GHCR)
        container = deploy_container(
            version="latest",
            name=container_name,
            port=8001,
            detach=True,
            remove=False,
        )

        assert container is not None
        assert container.name == container_name
        assert container.status in ["running", "created"]

        # Wait for container to be ready
        container.reload()
        assert container.status == "running"

    @pytest.mark.asyncio
    async def test_deploy_with_env_vars(self, docker_client, cleanup_container):
        """Test deploying with environment variable overrides."""
        container_name = "test-mcp-tef-env"
        cleanup_container.append(container_name)

        env_vars = {
            "LOG_LEVEL": "DEBUG",
            "DATABASE_URL": "sqlite:///./data/test.db",
        }

        container = deploy_container(
            version="latest",
            name=container_name,
            port=8002,
            env_vars=env_vars,
            detach=True,
            remove=False,
        )

        # Verify environment variables
        container.reload()
        container_env = container.attrs["Config"]["Env"]

        assert any("LOG_LEVEL=DEBUG" in e for e in container_env)
        assert any("DATABASE_URL=sqlite:///./data/test.db" in e for e in container_env)

    @pytest.mark.asyncio
    async def test_health_check_after_deploy(self, docker_client, cleanup_container):
        """Test health check after container deployment."""
        container_name = "test-mcp-tef-health"
        cleanup_container.append(container_name)

        # Deploy container
        deploy_container(
            version="latest",
            name=container_name,
            port=8003,
            detach=True,
            remove=False,
        )

        # Wait for server to be ready using health check polling
        # verify_ssl=False for self-signed certificates
        success, _ = await check_health(
            "https://localhost:8003", timeout=TEST_HEALTH_TIMEOUT, verify_ssl=False
        )
        assert success, "Server failed to become healthy within timeout"

        # Test HTTPS connectivity (mcp-tef uses self-signed TLS by default)
        config = ClientConfig(base_url="https://localhost:8003", verify_ssl=False)
        client = TefClient(config)

        try:
            health_response = await client.health()
            assert health_response.status == "healthy"
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_deploy_local_image(self, docker_client, cleanup_container):
        """Test deploying a locally built image.

        This test uses the same GHCR image but accessed via --image parameter
        to verify the local image code path works correctly.
        """
        container_name = "test-mcp-tef-local"
        cleanup_container.append(container_name)

        # Use custom image parameter (using the already-pulled GHCR image)
        container = deploy_container(
            image="ghcr.io/stackloklabs/mcp-tef:latest",
            name=container_name,
            port=8004,
            detach=True,
            remove=False,
        )

        assert container is not None
        assert container.status in ["running", "created"]

    @pytest.mark.asyncio
    async def test_deploy_custom_port(self, docker_client, cleanup_container):
        """Test custom port mapping."""
        container_name = "test-mcp-tef-port"
        cleanup_container.append(container_name)

        custom_port = 9999

        container = deploy_container(
            version="latest",
            name=container_name,
            port=custom_port,
            detach=True,
            remove=False,
        )

        # Verify port mapping
        container.reload()
        port_bindings = container.attrs["NetworkSettings"]["Ports"]
        assert "8000/tcp" in port_bindings
        assert port_bindings["8000/tcp"][0]["HostPort"] == str(custom_port)

    @pytest.mark.asyncio
    async def test_deploy_replaces_existing(self, docker_client, cleanup_container):
        """Test that deploying replaces existing container with same name."""
        container_name = "test-mcp-tef-replace"
        cleanup_container.append(container_name)

        # Deploy first container
        container1 = deploy_container(
            version="latest",
            name=container_name,
            port=8005,
            detach=True,
            remove=False,
        )

        container1_id = container1.id

        # Deploy second container with same name
        container2 = deploy_container(
            version="latest",
            name=container_name,
            port=8005,
            detach=True,
            remove=False,
        )

        container2_id = container2.id

        # Verify different containers
        assert container1_id != container2_id

        # Verify first container is removed
        with pytest.raises(docker.errors.NotFound):
            docker_client.containers.get(container1_id)

    @pytest.mark.asyncio
    async def test_api_client_connectivity(self, docker_client, cleanup_container):
        """Test API client can connect to deployed server."""
        container_name = "test-mcp-tef-api"
        cleanup_container.append(container_name)

        # Deploy container
        deploy_container(
            version="latest",
            name=container_name,
            port=8006,
            detach=True,
            remove=False,
        )

        # Wait for server to be ready using health check polling
        # verify_ssl=False for self-signed certificates
        success, _ = await check_health(
            "https://localhost:8006", timeout=TEST_HEALTH_TIMEOUT, verify_ssl=False
        )
        assert success, "Server failed to become healthy within timeout"

        # Test API client (mcp-tef uses self-signed TLS by default)
        config = ClientConfig(base_url="https://localhost:8006", verify_ssl=False)
        client = TefClient(config)

        try:
            # Test health endpoint
            health = await client.health()
            assert health.status == "healthy"

            # Test info endpoint
            info = await client.info()
            assert info.name == "MCP Tool Evaluation System"
            assert info.version is not None

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_check_health_function(self):
        """Test health check function with mock server."""
        # This test would require a mock HTTP server
        # For now, we just test that the function is callable
        success, data = await check_health("http://localhost:99999", timeout=1)
        assert success is False
        assert data is None


class TestStopCommand:
    """Test stop command functionality.

    Note: These tests require:
    1. Docker daemon running
    2. Access to GHCR or a locally built image (ghcr.io/stackloklabs/mcp-tef:latest)

    To run these tests:
    1. Pull image: docker pull ghcr.io/stackloklabs/mcp-tef:latest
    2. Run: pytest tests/integration/test_cli_deploy.py::TestStopCommand -v
    """

    def test_stop_running_container(self, docker_client, cleanup_container):
        """Test stopping a running container."""
        from click.testing import CliRunner

        from mcp_tef_cli.commands.stop import stop

        container_name = "test-mcp-tef-stop"
        cleanup_container.append(container_name)

        # Deploy a container first
        deploy_container(
            version="latest",
            name=container_name,
            port=8010,
            detach=True,
            remove=False,
        )

        # Verify container is running
        container = docker_client.containers.get(container_name)
        assert container.status == "running"

        # Stop the container using CLI command
        runner = CliRunner()
        result = runner.invoke(stop, ["--name", container_name])

        assert result.exit_code == 0
        assert "stopped" in result.output.lower() or "Cleanup complete" in result.output

        # Verify container is removed
        with pytest.raises(docker.errors.NotFound):
            docker_client.containers.get(container_name)

    def test_stop_nonexistent_container(self):
        """Test stopping a container that doesn't exist."""
        from click.testing import CliRunner

        from mcp_tef_cli.commands.stop import stop

        runner = CliRunner()
        result = runner.invoke(stop, ["--name", "nonexistent-container-12345"])

        # Should not fail, just warn
        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    def test_stop_with_force(self, docker_client, cleanup_container):
        """Test force stopping a container."""
        from click.testing import CliRunner

        from mcp_tef_cli.commands.stop import stop

        container_name = "test-mcp-tef-force-stop"
        cleanup_container.append(container_name)

        # Deploy a container first
        deploy_container(
            version="latest",
            name=container_name,
            port=8011,
            detach=True,
            remove=False,
        )

        # Force stop the container
        runner = CliRunner()
        result = runner.invoke(stop, ["--name", container_name, "--force"])

        assert result.exit_code == 0
        assert "killed" in result.output.lower() or "Cleanup complete" in result.output

        # Verify container is removed
        with pytest.raises(docker.errors.NotFound):
            docker_client.containers.get(container_name)

    def test_stop_already_stopped_container(self, docker_client, cleanup_container):
        """Test stopping a container that is already stopped."""
        from click.testing import CliRunner

        from mcp_tef_cli.commands.stop import stop

        container_name = "test-mcp-tef-already-stopped"
        cleanup_container.append(container_name)

        # Deploy and then manually stop the container
        container = deploy_container(
            version="latest",
            name=container_name,
            port=8012,
            detach=True,
            remove=False,
        )
        container.stop()

        # Try to stop it again via CLI
        runner = CliRunner()
        result = runner.invoke(stop, ["--name", container_name])

        assert result.exit_code == 0
        assert "not running" in result.output.lower() or "removed" in result.output.lower()

        # Verify container is removed
        with pytest.raises(docker.errors.NotFound):
            docker_client.containers.get(container_name)
