"""Unit tests for parsing functions (no Docker required)."""

import pytest

from mcp_tef_cli.docker_client import (
    _is_named_volume,
    parse_env_vars,
    parse_volumes,
    validate_port,
)


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

    def test_parse_env_vars_empty_value(self):
        """Test parsing environment variable with empty value."""
        env_list = ["KEY1=", "KEY2=value"]
        env_vars = parse_env_vars(env_list, None)

        assert env_vars == {"KEY1": "", "KEY2": "value"}

    def test_parse_env_vars_value_with_equals(self):
        """Test parsing environment variable with equals in value."""
        env_list = ["KEY1=value=with=equals"]
        env_vars = parse_env_vars(env_list, None)

        assert env_vars == {"KEY1": "value=with=equals"}


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

    def test_parse_volumes_named_volume(self):
        """Test parsing named volume (no host path validation)."""
        volume_list = ["myvolume:/container/path"]
        volumes = parse_volumes(volume_list)

        assert volumes == {"myvolume": {"bind": "/container/path", "mode": "rw"}}

    def test_parse_volumes_named_volume_with_mode(self):
        """Test parsing named volume with mode."""
        volume_list = ["data_volume:/app/data:ro"]
        volumes = parse_volumes(volume_list)

        assert volumes == {"data_volume": {"bind": "/app/data", "mode": "ro"}}


class TestNamedVolumeDetection:
    """Test named volume detection."""

    def test_is_named_volume_simple(self):
        """Test simple named volume."""
        assert _is_named_volume("myvolume") is True
        assert _is_named_volume("data_volume") is True
        assert _is_named_volume("test-volume") is True

    def test_is_named_volume_with_path(self):
        """Test paths are not named volumes."""
        assert _is_named_volume("/absolute/path") is False
        assert _is_named_volume("./relative/path") is False
        assert _is_named_volume("../parent/path") is False

    def test_is_named_volume_invalid_start(self):
        """Test invalid starting characters."""
        assert _is_named_volume("-starts-with-dash") is False
        assert _is_named_volume(".starts-with-dot") is False

    def test_is_named_volume_empty(self):
        """Test empty string."""
        assert _is_named_volume("") is False


class TestPortValidation:
    """Test port validation."""

    def test_validate_port_valid(self):
        """Test valid port numbers."""
        validate_port(80)
        validate_port(443)
        validate_port(8000)
        validate_port(1)
        validate_port(65535)

    def test_validate_port_invalid_zero(self):
        """Test port 0 is invalid."""
        import click

        with pytest.raises(click.BadParameter, match="Port must be between"):
            validate_port(0)

    def test_validate_port_invalid_negative(self):
        """Test negative port is invalid."""
        import click

        with pytest.raises(click.BadParameter, match="Port must be between"):
            validate_port(-1)

    def test_validate_port_invalid_too_high(self):
        """Test port > 65535 is invalid."""
        import click

        with pytest.raises(click.BadParameter, match="Port must be between"):
            validate_port(65536)
