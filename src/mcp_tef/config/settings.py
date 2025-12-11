"""Application configuration management using Pydantic BaseSettings."""

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    CliSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from mcp_tef.models.enums import EmbeddingModelType

# Default Ollama base URL
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"

# Default system prompt for tool selection agents
DEFAULT_SYSTEM_PROMPT = """
You are a tool selection agent designed to identify the most appropriate tool for solving user
queries. Your primary function is to analyze user requests and recommend the single best tool to
address their needs.

Instructions:
- Analyze the user's query to understand their specific need or problem
- Select the most appropriate tool
- Use the chosen tool to generate a response to the user's query
""".strip()


class ModelSettings(BaseModel):
    """Configuration for a specific LLM model."""

    name: str = Field(
        ...,
        description="Model identifier (e.g., 'llama3.2:3b', 'anthropic/claude-3.5-sonnet')",
    )
    provider: str = Field(
        ...,
        description="Provider name (e.g., 'ollama', 'openrouter', 'openai', 'anthropic')",
    )
    base_url: str | None = Field(
        None,
        description=(
            "Base URL for the provider API. "
            "Required for ollama, optional for others (openrouter has built-in support)"
        ),
    )
    timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Request timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for failed requests",
    )


class Settings(BaseSettings):
    """Application settings with CLI, environment variable, and .env file support.

    Configuration hierarchy (highest to lowest priority):
    1. CLI arguments (e.g., --port 8080, --log-level DEBUG)
    2. Environment variables
    3. .env file
    4. Default values
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources to include CLI arguments.

        Priority order (highest to lowest):
        1. CLI arguments
        2. Environment variables
        3. .env file
        4. Default values
        """
        return (
            init_settings,
            CliSettingsSource(
                settings_cls,
                cli_parse_args=True,
                cli_ignore_unknown_args=True,
                cli_kebab_case=True,
            ),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    # LLM Model Configuration
    # Use nested ModelSettings for cleaner configuration management
    # Environment variables: DEFAULT_MODEL__NAME, DEFAULT_MODEL__PROVIDER, etc.
    default_model: ModelSettings = Field(
        default=ModelSettings(
            name="ebdm/gemma3-enhanced:12b",
            provider="ollama",
            base_url=DEFAULT_OLLAMA_BASE_URL,
            timeout=30,
            max_retries=3,
        ),
        description="Default LLM model (fallback when no DB models registered)",
    )

    default_system_prompt_tool_selection: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        description="Default system prompt for tool selection agents",
    )

    # Model Selection Preferences
    prefer_small_model_class: bool = Field(
        default=True,
        description=(
            "Prefer 'small' model class for simple operations (tool selection, confusion testing)"
        ),
    )

    prefer_frontier_model_class: bool = Field(
        default=True,
        description=(
            "Prefer 'frontier' model class for complex operations (recommendations, generation)"
        ),
    )

    # Database Configuration
    database_url: str = Field(
        default="sqlite:///./mcp_eval.db",
        description="SQLite database URL",
    )

    # Application Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    rich_tracebacks: bool = Field(
        default=False,
        description="Enable rich tracebacks in logs",
    )
    colored_logs: bool = Field(
        default=True,
        description="Enable colored logs in console output",
    )

    api_key_header_name: str = Field(
        default="X-Model-API-Key",
        description="HTTP header name for runtime API key (not persisted)",
    )

    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port for FastAPI server",
    )

    host: str = Field(
        default="0.0.0.0",  # nosec B104 - Intentionally binding to all interfaces for server
        description="Host address for FastAPI server",
    )
    reload_server: bool = Field(
        default=False,
        description="Enable auto-reload for FastAPI server (development only)",
    )

    # TLS/HTTPS Configuration
    tls_enabled: bool = Field(
        default=True,
        description="Enable TLS/HTTPS for the FastAPI server",
    )

    tls_cert_file: str | None = Field(
        default=None,
        description="Path to TLS certificate file (PEM format). Auto-generated if not provided.",
    )

    tls_key_file: str | None = Field(
        default=None,
        description="Path to TLS private key file (PEM format). Auto-generated if not provided.",
    )

    tls_auto_generate: bool = Field(
        default=True,
        description="Auto-generate self-signed certificate if cert/key files not provided",
    )

    tls_cert_dir: str = Field(
        default=".certs",
        description="Directory for storing auto-generated certificates",
    )

    # Provider API Keys
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key for LLM access",
    )

    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for embedding services (optional)",
    )

    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key (optional)",
    )

    # Embedding Configuration
    embedding_model_type: EmbeddingModelType = Field(
        default=EmbeddingModelType.FASTEMBED,
        description="Embedding model type: 'fastembed', 'openai', or 'custom'",
    )

    embedding_model_name: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description=(
            "Embedding model identifier (e.g., BAAI/bge-small-en-v1.5, text-embedding-3-small)"
        ),
    )

    custom_embedding_api_url: str = Field(
        default="",
        description="Custom embedding API URL (required if embedding_model_type='custom')",
    )

    similarity_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Default similarity threshold for flagging similar tools",
    )

    # MCP Server Configuration
    mcp_server_timeout: int = Field(
        default=60,
        ge=1,
        le=300,
        description="Timeout in seconds for MCP server connections and tool loading operations",
    )

    def get_base_url_for_provider(self, provider: str) -> str | None:
        """Get the base URL for a given provider.

        This method provides default base URLs for providers based on common patterns.
        It's primarily used when a model from the database doesn't specify a base_url.

        Args:
            provider: Provider name (e.g., 'ollama', 'openrouter', 'openai', 'anthropic')

        Returns:
            Base URL for the provider, or None if not needed
        """
        provider_lower = provider.lower()
        if provider_lower == "ollama":
            # Use default_model's base_url if it's an ollama provider, otherwise use default
            if self.default_model.provider.lower() == "ollama":
                return self.default_model.base_url
            return DEFAULT_OLLAMA_BASE_URL
        # OpenRouter has built-in support in Pydantic AI - no base_url needed
        # OpenAI and Anthropic also have built-in defaults
        return None


def get_settings() -> Settings:
    """Get application settings instance.

    Returns:
        Configured Settings object with environment variables loaded
    """
    import os

    # Manually override default_model if environment variables are set
    # Pydantic doesn't automatically parse nested BaseModel fields from env vars
    env_mapping = {
        "provider": ("DEFAULT_MODEL__PROVIDER", str),
        "name": ("DEFAULT_MODEL__NAME", str),
        "base_url": ("DEFAULT_MODEL__BASE_URL", str),
        "timeout": ("DEFAULT_MODEL__TIMEOUT", int),
        "max_retries": ("DEFAULT_MODEL__MAX_RETRIES", int),
    }

    model_overrides = {}
    for field_name, (env_var, type_func) in env_mapping.items():
        value = os.getenv(env_var)
        if value is not None:
            model_overrides[field_name] = type_func(value) if value else None

    if model_overrides:
        # Start with default values and merge overrides
        default_settings = Settings()
        default_model_dict = default_settings.default_model.model_dump()
        default_model_dict.update(model_overrides)
        custom_model = ModelSettings(**default_model_dict)
        return Settings(default_model=custom_model)

    return Settings()
