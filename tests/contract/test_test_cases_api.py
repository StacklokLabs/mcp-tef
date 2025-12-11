"""Contract tests for test case API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.fixture
def mcp_server_url() -> str:
    """Return a test MCP server URL (no persistence needed)."""
    return "http://localhost:3000"


@pytest.mark.asyncio
async def test_create_test_case(client: AsyncClient, mcp_server_url: str):
    """Test POST /test-cases endpoint creates a new test case."""
    # Mock MCPLoaderService for test case creation
    with patch("mcp_tef.api.test_cases.MCPLoaderService") as mock:
        mock_instance = mock.return_value
        mock_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "input_schema": {
                        "type": "object",
                        "properties": {"param": {"type": "string"}},
                    },
                }
            ]
        )

        payload = {
            "name": "Test weather query",
            "query": "What is the weather in San Francisco?",
            "expected_mcp_server_url": mcp_server_url,
            "expected_tool_name": "test_tool",
            "expected_parameters": {"location": "San Francisco"},
            "available_mcp_servers": [mcp_server_url],
        }

        response = await client.post("/test-cases", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["name"] == payload["name"]
        assert data["query"] == payload["query"]
        assert data["expected_mcp_server_url"] == mcp_server_url
        assert data["expected_tool_name"] == "test_tool"
        assert data["expected_parameters"] == payload["expected_parameters"]
        assert data["available_mcp_servers"] == [mcp_server_url]
        assert "created_at" in data


@pytest.mark.asyncio
async def test_create_test_case_missing_required_fields(client: AsyncClient, mcp_server_url: str):
    """Test creating test case without required tool fields fails validation."""
    with patch("mcp_tef.api.test_cases.MCPLoaderService") as mock:
        mock_instance = mock.return_value
        mock_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
                }
            ]
        )

        payload = {
            "name": "Missing required fields",
            "query": "Hello",
            "available_mcp_servers": [mcp_server_url],
        }

        response = await client.post("/test-cases", json=payload)

        # Should return 400 since expected_mcp_server_url and expected_tool_name
        # are optional but create validation issues
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_test_case_validation_errors(client: AsyncClient, mcp_server_url: str):
    """Test POST /test-cases with invalid data."""
    # Empty query
    payload = {
        "name": "Test",
        "query": "",
        "expected_mcp_server_url": mcp_server_url,
        "expected_tool_name": "test_tool",
        "available_mcp_servers": [mcp_server_url],
    }
    response = await client.post("/test-cases", json=payload)
    assert response.status_code == 422

    # Empty available_mcp_servers
    payload["query"] = "Test query"
    payload["available_mcp_servers"] = []
    response = await client.post("/test-cases", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_test_cases(client: AsyncClient, mcp_server_url: str):
    """Test GET /test-cases endpoint."""
    # Create test cases
    with patch("mcp_tef.api.test_cases.MCPLoaderService") as mock:
        mock_instance = mock.return_value
        mock_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
                }
            ]
        )

        for i in range(3):
            await client.post(
                "/test-cases",
                json={
                    "name": f"Test {i}",
                    "query": f"Query {i}",
                    "expected_mcp_server_url": mcp_server_url,
                    "expected_tool_name": "test_tool",
                    "available_mcp_servers": [mcp_server_url],
                },
            )

    response = await client.get("/test-cases")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) == 3
    assert data["total"] == 3


@pytest.mark.asyncio
async def test_get_test_case_by_id(client: AsyncClient, mcp_server_url: str):
    """Test GET /test-cases/{test_case_id} endpoint."""
    with patch("mcp_tef.api.test_cases.MCPLoaderService") as mock:
        mock_instance = mock.return_value
        mock_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
                }
            ]
        )

        create_response = await client.post(
            "/test-cases",
            json={
                "name": "Test case",
                "query": "Test query",
                "expected_mcp_server_url": mcp_server_url,
                "expected_tool_name": "test_tool",
                "available_mcp_servers": [mcp_server_url],
            },
        )
        test_case_id = create_response.json()["id"]

    response = await client.get(f"/test-cases/{test_case_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_case_id
    assert data["name"] == "Test case"


@pytest.mark.asyncio
async def test_delete_test_case(client: AsyncClient, mcp_server_url: str):
    """Test DELETE /test-cases/{test_case_id} endpoint."""
    with patch("mcp_tef.api.test_cases.MCPLoaderService") as mock:
        mock_instance = mock.return_value
        mock_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
                }
            ]
        )

        create_response = await client.post(
            "/test-cases",
            json={
                "name": "To delete",
                "query": "Test",
                "expected_mcp_server_url": mcp_server_url,
                "expected_tool_name": "test_tool",
                "available_mcp_servers": [mcp_server_url],
            },
        )
        test_case_id = create_response.json()["id"]

    response = await client.delete(f"/test-cases/{test_case_id}")
    assert response.status_code == 204

    get_response = await client.get(f"/test-cases/{test_case_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_test_run_ingests_tools_before_execution(client: AsyncClient, mcp_server_url: str):
    """Test POST /test-cases/{id}/run ingests tools before execution.

    Tool ingestion should happen during test run execution.
    """
    # Mock MCPLoaderService for test case creation and test execution
    with patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader:
        mock_loader_instance = mock_loader.return_value
        mock_loader_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "ingestion_tool",
                    "description": "Tool for ingestion test",
                    "input_schema": {"type": "object", "properties": {"param": {"type": "string"}}},
                }
            ]
        )

        # Create test case
        test_case_response = await client.post(
            "/test-cases",
            json={
                "name": "Ingestion test",
                "query": "Test tool ingestion",
                "expected_mcp_server_url": mcp_server_url,
                "expected_tool_name": "ingestion_tool",
                "available_mcp_servers": [mcp_server_url],
            },
        )
        assert test_case_response.status_code == 201
        test_case_id = test_case_response.json()["id"]

        # Execute test run
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

        # Verify MCPLoaderService was called during test execution
        # Should be called at least twice: once for test case creation, once for test run
        call_count = mock_loader_instance.load_tools_from_url.call_count
        assert call_count >= 2, f"Expected at least 2 calls, got {call_count}"


@pytest.mark.asyncio
async def test_test_execution_fails_on_unreachable_server_during_tool_ingestion(
    client: AsyncClient, mcp_server_url: str
):
    """Test execution fails gracefully when server is unreachable during tool ingestion.

    Tool ingestion errors should result in test run FAILED status.
    """
    # Mock MCPLoaderService for test case creation
    with patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader_api:
        mock_loader_api_instance = mock_loader_api.return_value
        mock_loader_api_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "Test tool",
                    "input_schema": {"type": "object"},
                }
            ]
        )

        # Create test case
        test_case_response = await client.post(
            "/test-cases",
            json={
                "name": "Unreachable server test",
                "query": "Test query",
                "expected_mcp_server_url": "http://localhost:9999",
                "expected_tool_name": "test_tool",
                "available_mcp_servers": ["http://localhost:9999"],
            },
        )
        assert test_case_response.status_code == 201
        test_case_id = test_case_response.json()["id"]

    # Mock MCPLoaderService for test execution to simulate connection failure
    with patch(
        "mcp_tef.services.mcp_loader.MCPLoaderService.load_tools_from_url",
        new_callable=AsyncMock,
    ) as mock_load:
        mock_load.side_effect = Exception("Connection refused: unreachable server")

        # Execute test run - should create run but fail during tool ingestion
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

        # Test run should still be created (201) but with failed status
        assert run_response.status_code == 201
        run_data = run_response.json()
        test_run_id = run_data["id"]

        # Get test run status
        status_response = await client.get(f"/test-runs/{test_run_id}")
        assert status_response.status_code == 200
        test_run = status_response.json()

        # Verify test run failed with appropriate error message
        assert test_run["status"] == "failed", "Test run should have failed status"
        assert "error_message" in test_run
        assert (
            "Connection refused" in test_run["error_message"]
            or "unreachable" in test_run["error_message"].lower()
        )
