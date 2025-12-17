"""Unit tests for LLMService with Pydantic AI integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_tef_models.schemas import MCPServerConfig
from pydantic_ai import ToolCallPart, ToolReturnPart

from mcp_tef.api.errors import LLMProviderError
from mcp_tef.models.llm_models import LLMResponse, LLMToolCall
from mcp_tef.services.llm_service import LLMService


@pytest.fixture
def llm_service():
    """Create LLMService instance for testing."""
    return LLMService(
        provider="openrouter",
        model="anthropic/claude-3.5-sonnet",
        api_key="test-api-key",
        timeout=30,
        max_retries=3,
    )


@pytest.fixture
def sample_mcp_server_urls():
    """Sample MCP server configs for testing."""
    return [MCPServerConfig(url="http://localhost:3000", transport="streamable-http")]


class TestLLMServiceInitialization:
    """Test LLMService initialization and Pydantic AI agent setup."""

    def test_init_does_not_create_agent_immediately(self):
        """Test that __init__ does not create agent until MCP servers are connected."""
        # Act
        service = LLMService(
            provider="openrouter",
            model="anthropic/claude-3.5-sonnet",
            api_key="test-key",
            timeout=30,
            max_retries=3,
        )

        # Assert
        assert service.agent is None  # Agent created only when connecting to MCP servers
        assert service.provider == "openrouter"
        assert service.model == "anthropic/claude-3.5-sonnet"
        assert service.api_key == "test-key"

    def test_init_stores_parameters(self, llm_service):
        """Test that __init__ stores all parameters correctly."""
        assert llm_service.provider == "openrouter"
        assert llm_service.model == "anthropic/claude-3.5-sonnet"
        assert llm_service.api_key == "test-api-key"
        assert llm_service.timeout == 30
        assert llm_service.max_retries == 3


class TestConnectToMCPServers:
    """Test connect_to_mcp_servers() functionality."""

    @pytest.mark.asyncio
    @patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP")
    @patch("mcp_tef.services.llm_service.Agent")
    async def test_connect_to_mcp_servers_creates_agent(
        self, mock_agent_class, mock_mcp_server_class, sample_mcp_server_urls
    ):
        """Test that connect_to_mcp_servers creates agent with MCP server toolsets."""
        # Arrange
        mock_mcp_instance = MagicMock()
        mock_mcp_server_class.return_value = mock_mcp_instance
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        service = LLMService(
            provider="openrouter",
            model="anthropic/claude-3.5-sonnet",
            api_key="test-key",
        )

        # Act
        await service.connect_to_mcp_servers(sample_mcp_server_urls, "")

        # Assert
        mock_mcp_server_class.assert_called_once_with("http://localhost:3000")
        mock_agent_class.assert_called_once()
        assert service.agent == mock_agent


class TestSelectToolWithToolCall:
    """Test select_tool() when LLM selects a tool."""

    @pytest.mark.asyncio
    @patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP")
    @patch("mcp_tef.services.llm_service.Agent")
    async def test_select_tool_returns_tool_call(
        self, mock_agent_class, mock_mcp_server_class, sample_mcp_server_urls
    ):
        """Test that select_tool returns LLMResponse with tool call."""
        # Arrange
        mock_mcp_instance = MagicMock()
        mock_mcp_server_class.return_value = mock_mcp_instance
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        # Mock Pydantic AI response with tool call and message parts
        mock_tool_call_part = MagicMock(spec=ToolCallPart)
        mock_tool_call_part.tool_name = "get_weather"
        mock_tool_call_part.args_as_dict = MagicMock(return_value={"location": "San Francisco"})
        mock_tool_call_part.timestamp = None

        mock_tool_return_part = MagicMock(spec=ToolReturnPart)
        mock_tool_return_part.tool_name = "get_weather"
        mock_tool_return_part.content = "Weather data"
        mock_tool_return_part.model_response_object = MagicMock(
            return_value={"temperature": 72, "condition": "sunny"}
        )
        mock_tool_return_part.timestamp = None

        mock_message_1 = MagicMock()
        mock_message_1.parts = [mock_tool_call_part]

        mock_message_2 = MagicMock()
        mock_message_2.parts = [mock_tool_return_part]

        mock_result = MagicMock()
        mock_result.all_messages = MagicMock(return_value=[mock_message_1, mock_message_2])
        mock_agent.run = AsyncMock(return_value=mock_result)

        service = LLMService(
            provider="openrouter",
            model="anthropic/claude-3.5-sonnet",
            api_key="test-key",
        )

        # Connect to MCP servers
        await service.connect_to_mcp_servers(sample_mcp_server_urls, "")

        # Act
        response = await service.select_tool(query="What's the weather in San Francisco?")

        # Assert
        assert isinstance(response, LLMResponse)
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "get_weather"
        assert response.tool_calls[0].parameters == {"location": "San Francisco"}
        assert response.raw_response is not None

    @pytest.mark.asyncio
    @patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP")
    @patch("mcp_tef.services.llm_service.Agent")
    async def test_select_tool_multiple_tool_calls(
        self, mock_agent_class, mock_mcp_server_class, sample_mcp_server_urls
    ):
        """Test that select_tool handles multiple tool calls."""
        # Arrange
        mock_mcp_instance = MagicMock()
        mock_mcp_server_class.return_value = mock_mcp_instance
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        # Mock multiple tool calls
        mock_tool_call_1 = MagicMock(spec=ToolCallPart)
        mock_tool_call_1.tool_name = "get_weather"
        mock_tool_call_1.args_as_dict = MagicMock(return_value={"location": "NYC"})
        mock_tool_call_1.timestamp = None

        mock_tool_return_1 = MagicMock(spec=ToolReturnPart)
        mock_tool_return_1.tool_name = "get_weather"
        mock_tool_return_1.content = "Weather data"
        mock_tool_return_1.model_response_object = MagicMock(return_value={"temp": 65})
        mock_tool_return_1.timestamp = None

        mock_tool_call_2 = MagicMock(spec=ToolCallPart)
        mock_tool_call_2.tool_name = "calculate"
        mock_tool_call_2.args_as_dict = MagicMock(return_value={"expression": "2+2"})
        mock_tool_call_2.timestamp = None

        mock_tool_return_2 = MagicMock(spec=ToolReturnPart)
        mock_tool_return_2.tool_name = "calculate"
        mock_tool_return_2.content = "4"
        mock_tool_return_2.model_response_object = MagicMock(return_value={"result": 4})
        mock_tool_return_2.timestamp = None

        mock_message_1 = MagicMock()
        mock_message_1.parts = [mock_tool_call_1]

        mock_message_2 = MagicMock()
        mock_message_2.parts = [mock_tool_return_1]

        mock_message_3 = MagicMock()
        mock_message_3.parts = [mock_tool_call_2]

        mock_message_4 = MagicMock()
        mock_message_4.parts = [mock_tool_return_2]

        mock_result = MagicMock()
        mock_result.all_messages = MagicMock(
            return_value=[mock_message_1, mock_message_2, mock_message_3, mock_message_4]
        )
        mock_agent.run = AsyncMock(return_value=mock_result)

        service = LLMService(provider="openrouter", model="test-model", api_key="key")
        await service.connect_to_mcp_servers(sample_mcp_server_urls, "")

        # Act
        response = await service.select_tool(query="Get weather and calculate 2+2")

        # Assert
        assert len(response.tool_calls) == 2
        assert response.tool_calls[0].name == "get_weather"
        assert response.tool_calls[1].name == "calculate"


class TestSelectToolWithoutToolCall:
    """Test select_tool() when LLM does not select a tool."""

    @pytest.mark.asyncio
    @patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP")
    @patch("mcp_tef.services.llm_service.Agent")
    async def test_select_tool_no_tool_call(
        self, mock_agent_class, mock_mcp_server_class, sample_mcp_server_urls
    ):
        """Test that select_tool returns LLMResponse without tool call."""
        # Arrange
        mock_mcp_instance = MagicMock()
        mock_mcp_server_class.return_value = mock_mcp_instance
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        # Mock text-only response (no tool calls)
        mock_text_part = MagicMock()
        mock_text_part.content = "Hello! How can I help you?"
        mock_text_part.timestamp = None

        mock_message = MagicMock()
        mock_message.parts = [mock_text_part]

        mock_result = MagicMock()
        mock_result.all_messages = MagicMock(return_value=[mock_message])
        mock_agent.run = AsyncMock(return_value=mock_result)

        service = LLMService(provider="openrouter", model="test-model", api_key="key")
        await service.connect_to_mcp_servers(sample_mcp_server_urls, "")

        # Act
        response = await service.select_tool(query="Hello!")

        # Assert
        assert isinstance(response, LLMResponse)
        assert len(response.tool_calls) == 0

    @pytest.mark.asyncio
    @patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP")
    @patch("mcp_tef.services.llm_service.Agent")
    async def test_select_tool_empty_mcp_servers(self, mock_agent_class, _mock_mcp_server_class):
        """Test select_tool with no MCP servers connected."""
        # Arrange
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        mock_result = MagicMock()
        mock_result.all_messages = MagicMock(return_value=[])
        mock_agent.run = AsyncMock(return_value=mock_result)

        service = LLMService(provider="openrouter", model="test-model", api_key="key")
        await service.connect_to_mcp_servers([], "")  # Empty MCP servers list

        # Act
        response = await service.select_tool(query="Get weather")

        # Assert
        assert len(response.tool_calls) == 0


class TestSelectToolErrorHandling:
    """Test error handling in select_tool()."""

    @pytest.mark.asyncio
    async def test_select_tool_requires_agent_initialization(self):
        """Test that select_tool raises error if agent not initialized."""
        # Arrange
        service = LLMService(provider="openrouter", model="test-model", api_key="key")

        # Act & Assert - should fail because agent is None
        with pytest.raises(LLMProviderError) as exc_info:
            await service.select_tool(query="Test query")

        assert "not initialized" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP")
    @patch("mcp_tef.services.llm_service.Agent")
    async def test_select_tool_raises_llm_provider_error(
        self, mock_agent_class, mock_mcp_server_class, sample_mcp_server_urls
    ):
        """Test that LLM failures raise LLMProviderError."""
        # Arrange
        mock_mcp_instance = MagicMock()
        mock_mcp_server_class.return_value = mock_mcp_instance
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_agent.run = AsyncMock(side_effect=Exception("API timeout"))

        service = LLMService(provider="openrouter", model="test-model", api_key="key")
        await service.connect_to_mcp_servers(sample_mcp_server_urls, "")

        # Act & Assert
        with pytest.raises(LLMProviderError) as exc_info:
            await service.select_tool(query="Test query")

        assert "openrouter" in str(exc_info.value).lower()
        assert "API timeout" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP")
    @patch("mcp_tef.services.llm_service.Agent")
    async def test_select_tool_handles_empty_response(
        self, mock_agent_class, mock_mcp_server_class, sample_mcp_server_urls
    ):
        """Test handling of empty LLM responses."""
        # Arrange
        mock_mcp_instance = MagicMock()
        mock_mcp_server_class.return_value = mock_mcp_instance
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        # Mock empty response
        mock_result = MagicMock()
        mock_result.all_messages = MagicMock(return_value=[])
        mock_agent.run = AsyncMock(return_value=mock_result)

        service = LLMService(provider="openrouter", model="test-model", api_key="key")
        await service.connect_to_mcp_servers(sample_mcp_server_urls, "")

        # Act - should handle gracefully (no exception)
        response = await service.select_tool(query="Test query")

        # Assert - should return valid response even with empty messages
        assert isinstance(response, LLMResponse)
        assert len(response.tool_calls) == 0


class TestSelectToolResponseStructure:
    """Test that LLMResponse has correct structure."""

    @pytest.mark.asyncio
    @patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP")
    @patch("mcp_tef.services.llm_service.Agent")
    async def test_llm_response_has_all_required_fields(
        self, mock_agent_class, mock_mcp_server_class, sample_mcp_server_urls
    ):
        """Test that LLMResponse contains all required fields."""
        # Arrange
        mock_mcp_instance = MagicMock()
        mock_mcp_server_class.return_value = mock_mcp_instance
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        mock_tool_call = MagicMock(spec=ToolCallPart)
        mock_tool_call.tool_name = "get_weather"
        mock_tool_call.args_as_dict = MagicMock(return_value={"location": "NYC"})
        mock_tool_call.timestamp = None

        mock_tool_return = MagicMock(spec=ToolReturnPart)
        mock_tool_return.tool_name = "get_weather"
        mock_tool_return.content = "Weather"
        mock_tool_return.model_response_object = MagicMock(return_value={})
        mock_tool_return.timestamp = None

        mock_msg1 = MagicMock()
        mock_msg1.parts = [mock_tool_call]

        mock_msg2 = MagicMock()
        mock_msg2.parts = [mock_tool_return]

        mock_result = MagicMock()
        mock_result.all_messages = MagicMock(return_value=[mock_msg1, mock_msg2])
        mock_agent.run = AsyncMock(return_value=mock_result)

        service = LLMService(provider="openrouter", model="test-model", api_key="key")
        await service.connect_to_mcp_servers(sample_mcp_server_urls, "")

        # Act
        response = await service.select_tool(query="Weather in NYC?")

        # Assert - verify all fields exist and have correct types
        assert isinstance(response, LLMResponse)
        assert hasattr(response, "tool_calls")
        assert hasattr(response, "raw_response")

        assert isinstance(response.tool_calls, list)
        assert isinstance(response.raw_response, str)

        if len(response.tool_calls) > 0:
            assert isinstance(response.tool_calls[0], LLMToolCall)
            assert isinstance(response.tool_calls[0].name, str)
            assert isinstance(response.tool_calls[0].parameters, dict)

    @pytest.mark.asyncio
    @patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP")
    @patch("mcp_tef.services.llm_service.Agent")
    async def test_raw_response_contains_formatted_output(
        self, mock_agent_class, mock_mcp_server_class, sample_mcp_server_urls
    ):
        """Test that raw_response contains formatted message parts."""
        # Arrange
        mock_mcp_instance = MagicMock()
        mock_mcp_server_class.return_value = mock_mcp_instance
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        mock_text_part = MagicMock()
        mock_text_part.content = "Test response"
        mock_text_part.timestamp = None

        mock_message = MagicMock()
        mock_message.parts = [mock_text_part]

        mock_result = MagicMock()
        mock_result.all_messages = MagicMock(return_value=[mock_message])
        mock_agent.run = AsyncMock(return_value=mock_result)

        service = LLMService(provider="openrouter", model="test-model", api_key="key")
        await service.connect_to_mcp_servers(sample_mcp_server_urls, "")

        # Act
        response = await service.select_tool(query="Test")

        # Assert - raw_response should be a non-empty string
        assert isinstance(response.raw_response, str)
        assert len(response.raw_response) > 0
