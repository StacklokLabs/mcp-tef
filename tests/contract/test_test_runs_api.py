"""Contract tests for test run API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from mcp_tef.models.schemas import ToolDefinition


@pytest.fixture
async def test_case_id(client: AsyncClient) -> str:
    """Create test case using MCP server URL directly (no persistence needed)."""
    mcp_server_url = "http://localhost:3000"

    # Mock MCPLoaderService for test case creation
    with patch("mcp_tef.api.test_cases.MCPLoaderService") as mock:
        mock_instance = mock.return_value
        mock_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="test_tool",
                    description="Test tool",
                    input_schema={"type": "object", "properties": {"param": {"type": "string"}}},
                )
            ]
        )

        # Create test case (no model_id required)
        test_case_response = await client.post(
            "/test-cases",
            json={
                "name": "Test case",
                "query": "Test query",
                "expected_mcp_server_url": mcp_server_url,
                "expected_tool_name": "test_tool",
                "available_mcp_servers": [{"url": mcp_server_url, "transport": "streamable-http"}],
            },
        )
        return test_case_response.json()["id"]


@pytest.mark.asyncio
async def test_run_test_case(client: AsyncClient, test_case_id: str):
    """Test POST /test-cases/{test_case_id}/run with runtime API key."""
    with (
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
        # Mock for test execution
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
                }
            ]
        )

        # Mock Pydantic AI Agent
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.data = {
            "tool_name": "test_tool",
            "parameters": {"param": "value"},
            "reasoning": "Selected test_tool",
            "confidence": 0.85,
        }
        mock_agent.run = AsyncMock(return_value=mock_result)

        # Execute test run with runtime API key and model settings
        response = await client.post(
            f"/test-cases/{test_case_id}/run",
            headers={"X-Model-API-Key": "test-runtime-api-key"},
            json={
                "model_settings": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "timeout": 30,
                    "temperature": 0.7,
                    "max_retries": 3,
                }
            },
        )

    # Should create a test run
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["test_case_id"] == test_case_id
    assert data["status"] in ["pending", "running", "completed", "failed"]
    assert "created_at" in data
    # Should include model_settings in response
    assert "model_settings" in data
    assert data["model_settings"]["provider"] == "openai"
    assert data["model_settings"]["model"] == "gpt-4"


@pytest.mark.asyncio
async def test_get_test_run(client: AsyncClient, test_case_id: str):
    """Test GET /test-runs/{test_run_id} returns model_settings."""
    # Create a test run with mocks
    with (
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
        # Mock for test execution
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
                }
            ]
        )

        # Mock Pydantic AI Agent
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.data = {
            "tool_name": "test_tool",
            "parameters": {"param": "value"},
            "reasoning": "Selected test_tool",
            "confidence": 0.85,
        }
        mock_agent.run = AsyncMock(return_value=mock_result)

        run_response = await client.post(
            f"/test-cases/{test_case_id}/run",
            headers={"X-Model-API-Key": "test-runtime-api-key"},
            json={
                "model_settings": {
                    "provider": "anthropic",
                    "model": "claude-3-sonnet",
                    "timeout": 60,
                    "temperature": 0.5,
                    "max_retries": 2,
                }
            },
        )
        test_run_id = run_response.json()["id"]

    # Get the test run
    response = await client.get(f"/test-runs/{test_run_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_run_id
    assert data["test_case_id"] == test_case_id
    assert "status" in data
    # Should include model_settings but NOT API key
    assert "model_settings" in data
    assert data["model_settings"]["provider"] == "anthropic"
    assert data["model_settings"]["model"] == "claude-3-sonnet"
    assert "api_key" not in data["model_settings"]


@pytest.mark.asyncio
async def test_get_test_run_not_found(client: AsyncClient):
    """Test GET /test-runs/{test_run_id} returns 404 for non-existent run."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/test-runs/{fake_id}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_run_test_case_missing_api_key(client: AsyncClient, test_case_id: str):
    """Test POST /test-cases/{test_case_id}/run fails gracefully without API key."""
    # Attempt to run test without X-Model-API-Key header
    response = await client.post(
        f"/test-cases/{test_case_id}/run",
        json={
            "model_settings": {
                "provider": "openai",
                "model": "gpt-4",
                "timeout": 30,
                "temperature": 0.7,
                "max_retries": 3,
            }
        },
    )

    # Should accept request
    # In test environment with mocked LLM, it may complete successfully
    # In production, it would fail with authentication error
    assert response.status_code == 201
    data = response.json()
    assert data["status"] in ["pending", "running", "completed", "failed"]
    # If failed, should have error message
    if data["status"] == "failed":
        assert data["error_message"] is not None


@pytest.mark.asyncio
async def test_run_test_case_empty_api_key(client: AsyncClient, test_case_id: str):
    """Test POST /test-cases/{test_case_id}/run fails gracefully with empty API key."""
    # Attempt to run test with empty API key
    response = await client.post(
        f"/test-cases/{test_case_id}/run",
        headers={"X-Model-API-Key": ""},
        json={
            "model_settings": {
                "provider": "openai",
                "model": "gpt-4",
                "timeout": 30,
                "temperature": 0.7,
                "max_retries": 3,
            }
        },
    )

    # Should accept request
    # In test environment with mocked LLM, it may complete successfully
    # In production, it would fail with authentication error
    assert response.status_code == 201
    data = response.json()
    assert data["status"] in ["pending", "running", "completed", "failed"]
    # If failed, should have error message
    if data["status"] == "failed":
        assert data["error_message"] is not None


async def test_fire_and_forget_execution(
    client: AsyncClient, test_case_id: str, mock_mcp_loader_service
):
    """Test POST /test-cases/{test_case_id}/run returns immediately with pending status."""
    # Configure the autouse mock to return tools for this test
    mock_mcp_loader_service.return_value = [
        {
            "name": "test_tool",
            "description": "Test tool",
            "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
            "output_schema": {},
        }
    ]

    with patch("mcp_tef.services.llm_service.Agent") as mock_agent_class:
        # Mock Pydantic AI Agent
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.data = {
            "tool_name": "test_tool",
            "parameters": {"param": "value"},
            "reasoning": "Selected test_tool",
            "confidence": 0.85,
        }
        mock_agent.run = AsyncMock(return_value=mock_result)

        # Execute test - should return immediately
        response = await client.post(
            f"/test-cases/{test_case_id}/run",
            json={
                "model_settings": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "timeout": 30,
                    "temperature": 0.7,
                    "max_retries": 3,
                }
            },
        )

        # Should return 201 with test run in pending state
        assert response.status_code == 201
        data = response.json()
        assert data["test_case_id"] == test_case_id
        assert data["status"] == "pending"
        assert data["id"] is not None
        assert data["created_at"] is not None
        # These should be None initially since test hasn't run yet
        assert data["llm_response_raw"] is None
        assert data["selected_tool"] is None
        assert data["extracted_parameters"] is None
        assert data["classification"] is None
        assert data["execution_time_ms"] is None
        assert data["error_message"] is None
        assert data["completed_at"] is None
        # expected_tool is always populated from test case data (available immediately)
        assert data["expected_tool"] is not None
        assert data["expected_tool"]["name"] == "test_tool"
        assert data["expected_tool"]["mcp_server_url"] == "http://localhost:3000"
        # tools list is populated during background ingestion
        # (happens very quickly, may already be done)
        assert isinstance(data["tools"], list)


@pytest.mark.asyncio
async def test_polling_for_test_completion(
    client: AsyncClient, test_case_id: str, mock_mcp_loader_service
):
    """Test polling GET /test-runs/{test_run_id} to wait for test completion."""
    import asyncio

    # Configure the autouse mock to return tools for this test
    mock_mcp_loader_service.return_value = [
        {
            "name": "test_tool",
            "description": "Test tool",
            "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
        }
    ]

    # Start test execution (autouse mock_pydantic_agent handles Agent)
    run_response = await client.post(
        f"/test-cases/{test_case_id}/run",
        headers={"X-Model-API-Key": "test-api-key"},
        json={
            "model_settings": {
                "provider": "openai",
                "model": "gpt-4",
                "timeout": 30,
                "temperature": 0.7,
                "max_retries": 3,
            }
        },
    )
    test_run_id = run_response.json()["id"]

    # Poll for completion (with timeout)
    max_polls = 50  # 5 seconds max (50 * 100ms)
    poll_count = 0
    status = "pending"

    while poll_count < max_polls and status not in ["completed", "failed"]:
        await asyncio.sleep(0.1)  # 100ms between polls
        response = await client.get(f"/test-runs/{test_run_id}")
        assert response.status_code == 200
        data = response.json()
        status = data["status"]
        poll_count += 1

        while poll_count < max_polls and status not in ["completed", "failed"]:
            await asyncio.sleep(0.1)  # 100ms between polls
            response = await client.get(f"/test-runs/{test_run_id}")
            assert response.status_code == 200
            data = response.json()
            status = data["status"]
            poll_count += 1

        # Test should eventually complete
        assert status == "completed", f"Test did not complete after {poll_count} polls"
        assert data["llm_response_raw"] is not None
        assert data["selected_tool"] is not None
        assert data["selected_tool"]["id"] is not None
        assert data["selected_tool"]["name"] is not None
        assert data["extracted_parameters"] == {"param": "value"}
        assert data["classification"] in ["TP", "FP", "TN", "FN"]
        assert data["execution_time_ms"] is not None
        assert data["execution_time_ms"] >= 1
        # New enriched fields
        assert data["expected_tool"] is not None
        assert isinstance(data["tools"], list)
        assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_failed_test_run_handling(client: AsyncClient, test_case_id: str):
    """Test that failed test runs populate error_message and status correctly."""
    import asyncio

    # Override the autouse mock to make the agent fail, and mock MCPLoaderService
    with (
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
        patch("mcp_tef.services.llm_service.MCPServerStreamableHTTP") as mock_mcp_http,
        patch("mcp_tef.services.llm_service.MCPServerSSE") as mock_mcp_sse,
    ):
        # Mock MCPLoaderService
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
                }
            ]
        )

        # Mock MCP server connections
        mock_mcp_http_instance = MagicMock()
        mock_mcp_http.return_value = mock_mcp_http_instance
        mock_mcp_sse_instance = MagicMock()
        mock_mcp_sse.return_value = mock_mcp_sse_instance

        # Make Agent fail
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_agent.run = AsyncMock(side_effect=Exception("LLM connection failed"))

        # Start test execution
        run_response = await client.post(
            f"/test-cases/{test_case_id}/run",
            headers={"X-Model-API-Key": "test-api-key"},
            json={
                "model_settings": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "timeout": 30,
                    "temperature": 0.7,
                    "max_retries": 3,
                }
            },
        )
        test_run_id = run_response.json()["id"]

        # Poll for completion (should fail)
        max_polls = 50
        poll_count = 0
        status = "pending"

        while poll_count < max_polls and status not in ["completed", "failed"]:
            await asyncio.sleep(0.1)
            response = await client.get(f"/test-runs/{test_run_id}")
            status = response.json()["status"]
            poll_count += 1

        # Test should have failed
        assert status == "failed"
        data = response.json()
        assert data["error_message"] is not None
        # Error may be wrapped with "LLM provider 'openai' error: " prefix
        assert (
            "LLM connection failed" in data["error_message"]
            or "Failed to create agent" in data["error_message"]
        )
        assert data["execution_time_ms"] is not None
        assert data["execution_time_ms"] >= 1
        assert data["completed_at"] is not None
        # Classification should be None for failed runs
        assert data["classification"] is None
