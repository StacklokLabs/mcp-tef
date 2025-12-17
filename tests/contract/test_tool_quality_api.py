"""Contract tests for MCP server tool quality API endpoint."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from dotenv import load_dotenv
from httpx import AsyncClient


@pytest.fixture
def anthropic_api_key():
    """Load ANTHROPIC_API_KEY from .env file.

    Returns:
        API key string from environment

    Raises:
        pytest.skip: If ANTHROPIC_API_KEY is not set or invalid in .env
    """
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        pytest.skip("ANTHROPIC_API_KEY not configured in .env file (must start with 'sk-ant-')")
    return api_key


@pytest.fixture
def openrouter_api_key():
    """Load OPENROUTER_API_KEY from .env file.

    Returns:
        API key string from environment

    Raises:
        pytest.skip: If OPENROUTER_API_KEY is not set or invalid in .env
    """
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or not api_key.startswith("sk-or-v1-"):
        pytest.skip("OPENROUTER_API_KEY not configured in .env file (must start with 'sk-or-v1-')")
    return api_key


@pytest.fixture
def mock_tools():
    """Create mock tool definitions returned by MCPLoaderService.

    Returns dictionaries in the format from load_tools_from_server (with input_schema).
    The service will convert these to ToolDefinition objects internally.
    """
    return [
        {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or zip code",
                    }
                },
                "required": ["location"],
            },
        },
        {
            "name": "calculate_distance",
            "description": "Calculate distance between two points",
            "input_schema": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Starting location"},
                    "end": {"type": "string", "description": "Ending location"},
                    "unit": {
                        "type": "string",
                        "enum": ["miles", "kilometers"],
                        "description": "Distance unit",
                    },
                },
                "required": ["start", "end"],
            },
        },
        {
            "name": "search_database",
            "description": "Search the database for records",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Maximum results to return"},
                },
                "required": ["query"],
            },
        },
    ]


@pytest.mark.asyncio
async def test_get_mcp_server_tool_quality_missing_api_key(
    test_app, client: AsyncClient, mock_tools: list[dict]
):
    """Test GET /mcp-servers/tools/quality handles missing API key gracefully.

    When no API key is provided via header and no fallback API keys are configured,
    the endpoint returns 200 with errors in the response (not an HTTP error).
    This is because the endpoint uses asyncio.gather with return_exceptions=True.
    """
    # Import the dependencies
    from mcp_tef.api.tool_quality import get_mcp_loader_service
    from mcp_tef.config.settings import Settings, get_settings

    # Create mock loader
    mock_loader = AsyncMock()
    mock_loader.load_tools_from_server = AsyncMock(return_value=mock_tools)

    # Create settings with no API keys (empty strings)
    mock_settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        anthropic_api_key="",
        openai_api_key="",
        openrouter_api_key="",
    )

    # Use FastAPI's dependency override system
    test_app.dependency_overrides[get_mcp_loader_service] = lambda: mock_loader
    test_app.dependency_overrides[get_settings] = lambda: mock_settings

    # Mock os.getenv to return None for all API key environment variables
    def mock_getenv(key: str, default=None):
        if key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
            return None
        return default

    try:
        # Patch os.getenv in the llm_service module where it's used
        with patch("mcp_tef.services.llm_service.os.getenv", side_effect=mock_getenv):
            # Call without X-Model-API-Key header and with Settings having no API keys
            response = await client.get(
                "/mcp-servers/tools/quality",
                params={
                    "server_urls": "http://localhost:3000/sse",
                    "model_provider": "anthropic",
                    "model_name": "claude-haiku-4-5-20251001",
                },
            )

            # Expect 200 but with errors in the response
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )

            # Verify response contains errors
            response_data = response.json()
            assert "errors" in response_data, "Response should have 'errors' field"
            assert response_data["errors"] is not None, "Errors should not be None"
            assert len(response_data["errors"]) > 0, "Should have at least one error"

            # Verify results are empty since evaluation failed
            assert "results" in response_data, "Response should have 'results' field"
            assert len(response_data["results"]) == 0, (
                "Results should be empty when evaluation fails"
            )
    finally:
        # Clean up dependency overrides
        test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_mcp_server_tool_quality_missing_query_params(
    client: AsyncClient, openrouter_api_key: str
):
    """Test GET /mcp-servers/tools/quality fails without query params."""
    # Missing server_urls
    response = await client.get(
        "/mcp-servers/tools/quality",
        params={
            "model_provider": "openrouter",
            "model_name": "anthropic/claude-3.5-sonnet",
        },
        headers={"X-Model-API-Key": openrouter_api_key},
    )
    assert response.status_code == 422

    # Missing model_provider
    response = await client.get(
        "/mcp-servers/tools/quality",
        params={
            "server_urls": "http://localhost:3000/sse",
            "model_name": "anthropic/claude-3.5-sonnet",
        },
        headers={"X-Model-API-Key": openrouter_api_key},
    )
    assert response.status_code == 422

    # Missing model_name
    response = await client.get(
        "/mcp-servers/tools/quality",
        params={
            "server_urls": "http://localhost:3000/sse",
            "model_provider": "openrouter",
        },
        headers={"X-Model-API-Key": openrouter_api_key},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.no_mock_agent  # Disable auto-mocking of Pydantic Agent for this test
async def test_get_mcp_server_tool_quality_by_url_multiple_urls(
    test_app,
    client: AsyncClient,
    anthropic_api_key: str,
    mock_tools: list[dict],
):
    """Test GET /mcp-servers/tools/quality evaluates multiple server URLs.

    This test validates that:
    1. The API accepts server_urls query parameter with comma-separated URLs
    2. The API processes multiple URLs concurrently
    3. Response contains evaluation results from all URLs
    4. Each result has populated evaluation dimensions (clarity, completeness, conciseness)

    Note: This test uses a real Anthropic API call (not mocked) to validate the integration.
    Requires ANTHROPIC_API_KEY in .env file.
    """
    # Import the dependencies
    from mcp_tef.api.tool_quality import get_mcp_loader_service

    # Create mock loader
    mock_loader = AsyncMock()
    mock_loader.load_tools_from_server = AsyncMock(return_value=mock_tools)

    # Use FastAPI's dependency override system
    test_app.dependency_overrides[get_mcp_loader_service] = lambda: mock_loader

    try:
        # Define two test URLs (they can be the same for testing purposes)
        url1 = "http://localhost:3000/sse"
        url2 = "http://localhost:3001/sse"
        server_urls = f"{url1},{url2}"

        # Call the API endpoint with multiple URLs (uses real Anthropic API)
        response = await client.get(
            "/mcp-servers/tools/quality",
            params={
                "server_urls": server_urls,
                "model_provider": "anthropic",
                "model_name": "claude-sonnet-4-5-20250929",
            },
            headers={"X-Model-API-Key": anthropic_api_key},
        )

        # Verify successful response
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        # Verify response structure
        data = response.json()
        assert "results" in data, "Response should contain 'results' field"
        results = data["results"]

        # Verify we got results for tools from both URLs
        # Each URL returns 3 tools, so we should have 6 results total
        expected_count = len(mock_tools) * 2
        assert len(results) == expected_count, (
            f"Expected {expected_count} results (3 tools × 2 URLs), got {len(results)}"
        )

        # Verify each result has proper structure
        for i, result in enumerate(results):
            # Verify basic structure
            assert "tool_name" in result, f"Result {i} missing 'tool_name'"
            assert "tool_description" in result, f"Result {i} missing 'tool_description'"
            assert "evaluation_result" in result, f"Result {i} missing 'evaluation_result'"

            # Verify tool info is populated
            assert result["tool_name"], f"Result {i} has empty tool_name"
            assert result["tool_description"], f"Result {i} has empty tool_description"

            eval_result = result["evaluation_result"]

            # Verify evaluation dimensions exist
            assert "clarity" in eval_result, f"Result {i} missing clarity dimension"
            assert "completeness" in eval_result, f"Result {i} missing completeness dimension"
            assert "conciseness" in eval_result, f"Result {i} missing conciseness dimension"

            # Verify each dimension has score and explanation
            for dimension_name in ["clarity", "completeness", "conciseness"]:
                dimension = eval_result[dimension_name]
                assert "score" in dimension, f"Result {i} {dimension_name} missing score"
                assert "explanation" in dimension, (
                    f"Result {i} {dimension_name} missing explanation"
                )

                # Verify score is in valid range (1-10)
                score = dimension["score"]
                assert isinstance(score, int), f"Result {i} {dimension_name} score should be int"
                assert 1 <= score <= 10, (
                    f"Result {i} {dimension_name} score should be 1-10, got {score}"
                )

        # Verify mock was called for both URLs
        call_count = mock_loader.load_tools_from_server.call_count
        assert call_count == 2, (
            f"Expected load_tools_from_server to be called twice, got {call_count}"
        )
        # Verify it was called with the correct URLs
        call_args_list = [call[0][0] for call in mock_loader.load_tools_from_server.call_args_list]
        assert url1 in call_args_list, f"Expected call with {url1}"
        assert url2 in call_args_list, f"Expected call with {url2}"
    finally:
        # Clean up dependency overrides
        test_app.dependency_overrides.clear()
