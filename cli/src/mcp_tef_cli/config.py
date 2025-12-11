"""Configuration management for mcp-tef CLI."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "CLIConfig",
    "load_config",
]


class CLIConfig(BaseSettings):
    """CLI configuration with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="TEF_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server settings
    server_url: str = Field(
        default="https://localhost:8000", description="Default mcp-tef server URL"
    )
    api_key: str | None = Field(default=None, description="API key for authentication")
    verify_ssl: bool = Field(default=False, description="Verify SSL certificates")

    # Docker settings
    docker_image: str = Field(
        default="ghcr.io/stackloklabs/mcp-tef", description="Default Docker image"
    )
    docker_version: str = Field(default="latest", description="Default image version")
    docker_port: int = Field(default=8000, description="Default container port")

    # Output settings
    output_format: str = Field(default="json", description="Default output format (json|table)")
    colored_output: bool = Field(default=True, description="Enable colored output")


def load_config() -> CLIConfig:
    """Load CLI configuration from environment and config files.

    Returns:
        CLIConfig instance with loaded settings
    """
    return CLIConfig()
