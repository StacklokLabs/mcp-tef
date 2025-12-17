"""Pytest fixtures for testing."""

import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from mcp_tef.api.app import app
from mcp_tef.config.settings import ModelSettings, Settings


@pytest.fixture
async def test_db():
    """Create an in-memory SQLite database for testing.

    Yields:
        Active in-memory database connection with schema initialized
    """
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row

    # Enable foreign key constraints
    await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()

    # Load and execute schema
    schema_path = Path(__file__).parent.parent / "src" / "mcp_tef" / "storage" / "schema.sql"
    with open(schema_path) as f:
        schema_sql = f.read()

    await db.executescript(schema_sql)
    await db.commit()

    yield db

    # Cleanup
    await db.close()


@pytest.fixture
def test_settings():
    """Create test settings.

    Returns:
        Settings configured for testing

    Environment Variables:
        USE_OLLAMA: Set to "true" to use Ollama instead of mock LLM
        OLLAMA_BASE_URL: Ollama API base URL (default: http://localhost:11434)
        OLLAMA_MODEL: Ollama model to use (default: llama3.2:1b)
    """
    use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"

    if use_ollama:
        # Use Ollama for more realistic LLM testing
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

        return Settings(
            openrouter_api_key="test-api-key",
            default_model=ModelSettings(
                name=ollama_model,
                provider="ollama",
                base_url=ollama_base_url,
                timeout=30,
                max_retries=3,
            ),
            database_url="sqlite:///:memory:",
            log_level="DEBUG",
            port=8000,
        )
    # Use mock LLM for fast, deterministic tests
    return Settings(
        openrouter_api_key="test-api-key",
        default_model=ModelSettings(
            name="anthropic/claude-3.5-sonnet",
            provider="openrouter",
            # No base_url needed - OpenRouter has built-in support in Pydantic AI
            timeout=30,
            max_retries=3,
        ),
        database_url="sqlite:///:memory:",
        log_level="DEBUG",
        port=8000,
    )


@pytest.fixture
async def test_app(test_db, test_settings):
    """Create FastAPI test application.

    Args:
        test_db: Test database fixture
        test_settings: Test settings fixture

    Yields:
        Configured FastAPI application with test database
    """
    # Override settings and db for testing
    app.state.settings = test_settings
    app.state.db = test_db

    yield app


@pytest.fixture
async def client(test_app):
    """Create async HTTP client for testing API endpoints.

    Args:
        test_app: Test application fixture

    Yields:
        Async HTTP client configured for test app
    """
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def mock_mcp_loader_service(request):
    """Automatically mock MCPLoaderService for all tests except unit tests.

    This fixture prevents actual network calls to MCP servers during tests.
    """
    # Skip mocking for unit tests - they handle their own mocking
    if "unit" in request.node.nodeid:
        yield None
        return

    with patch(
        "mcp_tef.services.mcp_loader.MCPLoaderService.load_tools_from_server",
        new_callable=AsyncMock,
    ) as mock_load:
        # Default mock returns empty list of tools
        mock_load.return_value = []
        yield mock_load


@pytest.fixture(autouse=True)
def mock_pydantic_agent(request):
    """Automatically mock Pydantic AI Agent for all tests except unit tests.

    This fixture is autouse=True, but excludes tests in tests/unit/ directory.
    It mocks the Agent initialization to prevent "Unknown model" errors in integration tests.
    """
    # Skip mocking for unit tests - they handle their own mocking
    if "unit" in request.node.nodeid:
        yield None
        return

    # Skip mocking for tests marked with @pytest.mark.no_mock_agent
    if request.node.get_closest_marker("no_mock_agent"):
        yield None
        return

    with (
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
        patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP") as mock_mcp_http,
        patch("mcp_tef.services.llm_service.MCPServerSSE") as mock_mcp_sse,
    ):
        # Mock MCP server connections
        mock_mcp_http_instance = MagicMock()
        mock_mcp_http.return_value = mock_mcp_http_instance

        mock_mcp_sse_instance = MagicMock()
        mock_mcp_sse.return_value = mock_mcp_sse_instance

        # Mock Agent
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent

        # Import Pydantic AI parts for proper spec
        from pydantic_ai import ToolCallPart, ToolReturnPart

        # Create mock tool call and return parts
        mock_tool_call_part = MagicMock(spec=ToolCallPart)
        mock_tool_call_part.tool_name = "test_tool"
        mock_tool_call_part.args_as_dict = MagicMock(return_value={"param": "value"})
        mock_tool_call_part.timestamp = None

        mock_tool_return_part = MagicMock(spec=ToolReturnPart)
        mock_tool_return_part.tool_name = "test_tool"
        mock_tool_return_part.content = "Test result"
        mock_tool_return_part.model_response_object = MagicMock(return_value={"result": "success"})
        mock_tool_return_part.timestamp = None

        # Mock message structure
        mock_message_1 = MagicMock()
        mock_message_1.parts = [mock_tool_call_part]

        mock_message_2 = MagicMock()
        mock_message_2.parts = [mock_tool_return_part]

        # Mock agent result
        mock_result = MagicMock()
        mock_result.all_messages = MagicMock(return_value=[mock_message_1, mock_message_2])
        mock_agent.run = AsyncMock(return_value=mock_result)

        yield {
            "agent_class": mock_agent_class,
            "agent": mock_agent,
            "mcp_http": mock_mcp_http,
            "mcp_sse": mock_mcp_sse,
        }


@pytest.fixture
async def test_provider_id(client):
    """Create a test provider and return its ID.

    Args:
        client: HTTP client fixture

    Returns:
        Provider ID string
    """
    response = await client.post(
        "/providers",
        json={
            "name": "test_provider",
            "api_key": "test-api-key",
            "base_url": "https://test-provider.example.com/api",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
async def test_model_id(client, test_provider_id):
    """Create a test model and return its ID.

    Args:
        client: HTTP client fixture
        test_provider_id: Provider ID from fixture

    Returns:
        Model ID string
    """
    response = await client.post(
        f"/providers/{test_provider_id}/models",
        json={
            "model_name": "anthropic/claude-3.5-sonnet",
            "display_name": "Claude 3.5 Sonnet",
            "timeout": 30,
            "max_retries": 3,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def test_mcp_server_url():
    """Return a test MCP server URL (no persistence needed).

    Returns:
        MCP server URL string
    """
    return "http://localhost:3000"


@pytest.fixture
async def test_run_id(client):
    """Create a test run and return its ID.

    This fixture provides a valid test_run_id for tests that create tools directly
    via the repository (simulating tool ingestion).

    Args:
        client: HTTP client fixture

    Returns:
        Test run ID string
    """
    # Mock tools for test case creation and test execution
    with patch("mcp_tef.api.test_cases.MCPLoaderService") as mock:
        mock_instance = mock.return_value
        mock_instance.load_tools_from_server = AsyncMock(
            return_value=[
                {
                    "name": "fixture_tool",
                    "description": "Tool for fixture",
                    "input_schema": {"type": "object"},
                }
            ]
        )

        # Create test case via API (using MCP server URL directly)
        test_case_response = await client.post(
            "/test-cases",
            json={
                "name": "Fixture test case",
                "query": "Test query for fixture",
                "expected_tool_calls": [
                    {
                        "mcp_server_url": "http://localhost:9999",
                        "tool_name": "fixture_tool",
                        "parameters": None,
                    }
                ],
                "available_mcp_servers": [
                    {"url": "http://localhost:9999", "transport": "streamable-http"}
                ],
            },
        )
        assert test_case_response.status_code == 201
        test_case_id = test_case_response.json()["id"]

        # Create test run
        run_response = await client.post(
            f"/test-cases/{test_case_id}/run",
            headers={"X-Model-API-Key": "test-key"},
            json={
                "model_settings": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "timeout": 30,
                    "temperature": 0.5,
                    "max_retries": 3,
                }
            },
        )
        assert run_response.status_code == 201
        return run_response.json()["id"]


@pytest.fixture
async def test_tool_id(client, test_mcp_server_url, test_run_id, test_db):
    """Create a test tool and return its ID.

    Args:
        client: HTTP client fixture
        test_mcp_server_url: MCP server URL from fixture
        test_run_id: Test run ID from fixture
        test_db: Test database fixture

    Returns:
        Tool ID string
    """
    from mcp_tef_models.schemas import ToolDefinitionCreate

    from mcp_tef.storage.tool_repository import ToolRepository

    tool_repo = ToolRepository(test_db)
    tool_data = ToolDefinitionCreate(
        name="test_tool",
        description="A test tool for unit testing",
        input_schema={
            "type": "object",
            "properties": {"param": {"type": "string", "description": "Test parameter"}},
            "required": ["param"],
        },
        mcp_server_url=test_mcp_server_url,
        test_run_id=test_run_id,
    )
    created_tool = await tool_repo.create(tool_data)
    return created_tool.id


@pytest.fixture
def tool_factory(test_db):
    """Factory fixture for creating test tools with custom parameters.

    Args:
        test_db: Test database fixture

    Returns:
        Async factory function that creates tools

    Example:
        tool = await tool_factory(
            server_id, test_run_id, "get_weather", description="Get weather info"
        )
    """
    from mcp_tef_models.schemas import ToolDefinitionCreate

    from mcp_tef.storage.tool_repository import ToolRepository

    async def _create_tool(
        mcp_server_url: str, test_run_id: str, name: str = "test_tool", **kwargs
    ):
        """Create a tool with custom parameters.

        Args:
            mcp_server_url: URL of the MCP server
            test_run_id: ID of the test run
            name: Tool name (default: "test_tool")
            **kwargs: Additional tool parameters
                (description, input_schema, output_schema)

        Returns:
            Created tool response
        """
        tool_repo = ToolRepository(test_db)
        tool_data = ToolDefinitionCreate(
            name=name,
            description=kwargs.get("description", f"Test tool: {name}"),
            input_schema=kwargs.get("input_schema", {"type": "object"}),
            output_schema=kwargs.get("output_schema"),
            mcp_server_url=mcp_server_url,
            test_run_id=test_run_id,
        )
        return await tool_repo.create(tool_data)

    return _create_tool


async def wait_for_test_run_completion(
    client: AsyncClient, test_run_id: str, max_polls: int = 50
) -> str:
    """Wait for a test run to complete (fire-and-forget execution).

    Args:
        client: HTTP client
        test_run_id: Test run ID to wait for
        max_polls: Maximum number of polls (default: 50, 5 seconds at 100ms intervals)

    Returns:
        Final status of test run ("completed" or "failed")

    Example:
        status = await wait_for_test_run_completion(client, test_run_id)
        assert status == "completed"
    """
    import asyncio

    poll_count = 0
    status = "pending"

    while poll_count < max_polls and status not in ["completed", "failed"]:
        await asyncio.sleep(0.1)  # 100ms between polls
        response = await client.get(f"/test-runs/{test_run_id}")
        status = response.json()["status"]
        poll_count += 1

    return status


@contextmanager
def mock_test_execution(tools_list):
    """Context manager for mocking test execution with MCPLoaderService and Pydantic AI.

    Args:
        tools_list: List of tool definitions to return from MCPLoaderService

    Example:
        with mock_test_execution([{"name": "test_tool", ...}]):
            response = await client.post(f"/test-cases/{test_case_id}/run")
    """
    with (
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
        # Mock MCPLoaderService for test execution
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(return_value=tools_list)

        # Mock Pydantic AI Agent
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_result = MagicMock()

        # Default to selecting first tool if tools available
        if tools_list:
            first_tool = tools_list[0]
            mock_result.data = {
                "tool_name": first_tool["name"],
                "parameters": {"test_param": "test_value"},
                "reasoning": f"Selected {first_tool['name']} for test execution",
                "confidence": 0.85,
            }
        else:
            mock_result.data = {
                "tool_name": None,
                "parameters": None,
                "reasoning": "No tools available",
                "confidence": 0.95,
            }

        mock_agent.run = AsyncMock(return_value=mock_result)

        yield
