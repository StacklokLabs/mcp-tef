"""LLM service for tool selection using Pydantic AI."""

import os
from collections.abc import Sequence
from typing import Any

import structlog
from mcp_tef_models.schemas import MCPServerConfig
from pydantic import BaseModel, Field
from pydantic_ai import (
    Agent,
    AgentRunResult,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.builtin_tools import AbstractBuiltinTool
from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.tools import Tool
from pydantic_ai.toolsets.abstract import AbstractToolset

from mcp_tef.api.errors import LLMProviderAPIKeyError, LLMProviderError
from mcp_tef.config.settings import DEFAULT_OLLAMA_BASE_URL, Settings
from mcp_tef.models.llm_models import ConfidenceLevel, LLMResponse, LLMToolCall

logger = structlog.get_logger(__name__)


class ToolSelectionResult(BaseModel):
    """Structured result for tool selection with confidence."""

    confidence: ConfidenceLevel = Field(
        ...,
        description=(
            "Your confidence level in the tool selection: 'high' if you're certain "
            "the tool matches the query well, 'low' if you're uncertain or the query or "
            "tool description are ambiguous."
        ),
    )


class LLMService:
    """Service for interacting with LLMs via Pydantic AI."""

    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str | None,
        timeout: int = 30,
        max_retries: int = 3,
        base_url: str | None = None,
        settings: Settings | None = None,
    ):
        """Initialize LLM service.

        Args:
            provider: LLM provider name
            model: Model identifier
            api_key: API key
            timeout: Request timeout
            max_retries: Maximum retry attempts
            base_url: Base URL for API endpoint (required for ollama, openrouter, etc.)
            settings: Application settings (optional, for fallback API keys)
        """
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = base_url
        self.settings = settings
        self.agent = None  # Will be initialized when connecting to MCP servers

    async def connect_to_mcp_servers(
        self, mcp_servers: list[MCPServerConfig], system_prompt: str
    ) -> None:
        """Connect to MCP servers and initialize the agent with toolsets.

        Args:
            mcp_servers: List of MCP server configs with 'name', 'url', 'transport'

        Raises:
            LLMProviderError: If connection fails
        """
        logger.info(f"Connecting to {len(mcp_servers)} MCP servers")

        try:
            toolsets = []
            for server in mcp_servers:
                # Currently support sse and streamable-http (similarly in MCPLoaderService)
                if server.transport == "sse":
                    mcp_server = MCPServerSSE(server.url)
                    toolsets.append(mcp_server)
                else:
                    mcp_server = MCPServerStreamableHTTP(server.url)
                    toolsets.append(mcp_server)

            # Initialize agent with all MCP server toolsets and structured output for confidence
            self.agent = self.make_agent(
                system_prompt=system_prompt, toolsets=toolsets, output_type=ToolSelectionResult
            )

            logger.info(f"Initialized agent with {len(toolsets)} MCP server toolsets")
        except LLMProviderError:
            raise
        except Exception as e:
            logger.error(f"Failed to connect to MCP servers: {e}")
            raise LLMProviderError(
                self.provider, f"Failed to connect to MCP servers: {str(e)}", e
            ) from e

    def _format_prompt_part(
        self, title: str, content: str | dict[str, Any] | Any, timestamp: str | None
    ) -> str:
        """Format a prompt part for logging.

        Args:
            title: Section title
            content: Content to format (will be converted to string)
            timestamp: Optional timestamp

        Returns:
            Formatted string
        """
        timestamp_str = str(timestamp) if timestamp is not None else "N/A"
        content_str = str(content) if content is not None else ""
        return f"\n{'-' * 30} {title} {'-' * 30}\n\nTimestamp: {timestamp_str}\n{content_str}\n"

    def _parse_agent_messages(self, result: AgentRunResult) -> tuple[list[LLMToolCall], str]:
        """Parse agent messages to extract tool calls and raw response.

        Args:
            result: Pydantic AI agent result object

        Returns:
            Tuple of (tool_calls, raw_response)

        Raises:
            LLMProviderError: If message parsing fails
        """
        current_tool_call = None
        current_tool_name = None
        tool_calls = []
        raw_response = ""

        for message in result.all_messages():
            for part in message.parts:
                timestamp = getattr(part, "timestamp", None)
                match part:
                    case SystemPromptPart():
                        raw_response += self._format_prompt_part(
                            "SYSTEM PROMPT", part.content, timestamp
                        )
                    case UserPromptPart():
                        raw_response += self._format_prompt_part(
                            "USER PROMPT", part.content, timestamp
                        )
                    case ToolReturnPart():
                        raw_response += self._format_prompt_part(
                            f"TOOL RETURN. TOOL: {part.tool_name}", part.content, timestamp
                        )
                        if current_tool_call is None or current_tool_name is None:
                            raise LLMProviderError(
                                self.provider,
                                "Tool return found without corresponding tool call",
                            )
                        tool_call = LLMToolCall(
                            name=current_tool_name,
                            parameters=current_tool_call,
                            response=part.model_response_object(),
                        )
                        tool_calls.append(tool_call)
                        current_tool_call = None
                        current_tool_name = None
                    case TextPart():
                        raw_response += self._format_prompt_part(
                            "RESPONSE TEXT", part.content, timestamp
                        )
                    case RetryPromptPart():
                        raw_response += self._format_prompt_part(
                            f"TOOL RETRY RETURN. TOOL: {part.tool_name}",
                            part.content,
                            timestamp,
                        )
                    case ToolCallPart():
                        raw_response += self._format_prompt_part(
                            f"TOOL CALL. TOOL: {part.tool_name}", part.args, timestamp
                        )
                        # If there's a pending tool call without a return, complete it first
                        if current_tool_call is not None and current_tool_name is not None:
                            logger.warning(
                                "Tool call without corresponding return, completing previous call",
                                previous_tool=current_tool_name,
                                new_tool=part.tool_name,
                            )
                            tool_calls.append(
                                LLMToolCall(
                                    name=current_tool_name,
                                    parameters=current_tool_call,
                                    response=None,
                                )
                            )
                        current_tool_call = part.args_as_dict()
                        current_tool_name = part.tool_name
                    case ThinkingPart():
                        raw_response += self._format_prompt_part(
                            "THINKING", part.content, timestamp
                        )
                    case _:
                        raw_response += self._format_prompt_part(
                            "UNIDENTIFIED PART", type(part).__name__, timestamp
                        )

        return tool_calls, raw_response

    async def select_tool(self, query: str) -> LLMResponse:
        """Ask LLM to select a tool for the given query.

        Args:
            query: User query

        Returns:
            LLM response with tool selection

        Raises:
            LLMProviderError: If LLM request fails
        """
        if self.agent is None:
            raise LLMProviderError(
                self.provider,
                "Agent not initialized. Call connect_to_mcp_servers() first.",
                None,
            )

        logger.info("Querying LLM with MCP server tools")

        try:
            # The agent will automatically have access to all tools from connected MCP servers
            result = await self.agent.run(query)

            # Parse messages to extract tool calls and raw response
            tool_calls, raw_response = self._parse_agent_messages(result)

            confidence_level = None
            if result.output and isinstance(result.output, ToolSelectionResult):
                confidence_level = result.output.confidence

            # Extract confidence level from structured output
            return LLMResponse(
                tool_calls=tool_calls,
                confidence_level=confidence_level,
                raw_response=raw_response,
            )

        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            raise LLMProviderError(self.provider, f"Failed to query LLM: {str(e)}", e) from e

    def make_agent(
        self,
        system_prompt: str,
        tools: Sequence[Tool] = (),
        builtin_tools: Sequence[AbstractBuiltinTool] = (),
        toolsets: Sequence[AbstractToolset] | None = None,
        output_type: type[BaseModel] | None = None,
    ) -> Agent:
        """
        Initializes a pydantic_ai Agent with the specified system prompt and tools.

        The api key for the model providers is determined with the following priority:
            self.api_key (generally from request header) ->
            env variable (from deployment) ->
            Settings value (default, though it may also be from deployment)
        """
        # Import here to avoid circular dependencies
        from pydantic_ai.exceptions import UserError

        # TODO support other providers
        model: Model | None = None
        try:
            if self.provider.lower() == "anthropic":
                api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
                if not api_key and self.settings:
                    api_key = self.settings.anthropic_api_key
                if not api_key:
                    raise LLMProviderAPIKeyError(
                        self.provider,
                        (
                            "API key required. "
                            "Provide via X-Model-API-Key header, set "
                            "ANTHROPIC_API_KEY environment variable, or configure in settings."
                        ),
                    )
                provider = AnthropicProvider(api_key=api_key)
                model = AnthropicModel(self.model, provider=provider)
            elif self.provider.lower() == "openai":
                api_key = self.api_key or os.getenv("OPENAI_API_KEY")
                if not api_key and self.settings:
                    api_key = self.settings.openai_api_key
                if not api_key:
                    raise LLMProviderAPIKeyError(
                        self.provider,
                        (
                            "API key required. "
                            "Provide via X-Model-API-Key header, set "
                            "OPENAI_API_KEY environment variable, or configure in settings."
                        ),
                    )
                provider = OpenAIProvider(api_key=api_key, base_url=self.base_url)
                model = OpenAIChatModel(self.model, provider=provider)
            elif self.provider.lower() == "openrouter":
                # OpenRouter has built-in support in Pydantic AI - no base_url needed
                api_key = self.api_key or os.getenv("OPENROUTER_API_KEY")
                if not api_key and self.settings:
                    api_key = self.settings.openrouter_api_key
                if not api_key:
                    raise LLMProviderAPIKeyError(
                        self.provider,
                        (
                            "API key required. "
                            "Provide via X-Model-API-Key header, set "
                            "OPENROUTER_API_KEY environment variable, or configure in settings."
                        ),
                    )
                provider = OpenRouterProvider(api_key=api_key)
                model = OpenAIChatModel(self.model, provider=provider)
            elif self.provider.lower() == "ollama":
                # Ollama uses OpenAIProvider with custom base_url
                # Ollama doesn't require an API key, but OpenAIProvider needs one (use empty string)
                api_key = self.api_key or os.getenv("OPENAI_API_KEY") or ""
                if not api_key and self.settings:
                    api_key = self.settings.openai_api_key or ""
                # Ensure base_url is set for Ollama - required!
                ollama_base_url = self.base_url or DEFAULT_OLLAMA_BASE_URL
                logger.info(f"Using Ollama with base_url: {ollama_base_url}, model: {self.model}")
                provider = OpenAIProvider(api_key=api_key, base_url=ollama_base_url)
                model = OpenAIChatModel(self.model, provider=provider)
            else:
                raise LLMProviderError(self.provider, "Unsupported provider")

            return Agent(
                model=model,
                output_type=output_type,
                system_prompt=system_prompt,
                tools=tools,
                builtin_tools=builtin_tools,
                toolsets=toolsets,
            )
        except UserError as e:
            # Catch Pydantic AI UserError and convert to our error type
            # If it's an API key issue, use LLMProviderAPIKeyError (400),
            # otherwise LLMProviderError (503)
            error_msg = str(e)
            if "api" in error_msg.lower() and "key" in error_msg.lower():
                raise LLMProviderAPIKeyError(self.provider, error_msg) from e
            raise LLMProviderError(self.provider, error_msg, e) from e
