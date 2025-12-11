"""Integration tests for complete tool selection workflow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tool_selection_workflow(client: AsyncClient, test_mcp_server_url: str):
    """Test complete workflow from tool setup to test execution with runtime API key."""
    # Mock MCPLoaderService for both test case creation AND test execution
    with (
        patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader_api,
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
        # Mock for test case creation (API layer)
        mock_loader_api_instance = mock_loader_api.return_value
        mock_loader_api_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "A test tool for unit testing",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "param": {"type": "string", "description": "Test parameter"}
                        },
                        "required": ["param"],
                    },
                }
            ]
        )

        # Mock for test execution (EvaluationService layer)
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "A test tool for unit testing",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "param": {"type": "string", "description": "Test parameter"}
                        },
                        "required": ["param"],
                    },
                }
            ]
        )

        # Mock Pydantic AI Agent
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.data = {
            "tool_name": "test_tool",
            "parameters": {"param": "test_value"},
            "reasoning": "Selected test_tool for the query",
            "confidence": 0.9,
        }
        mock_agent.run = AsyncMock(return_value=mock_result)

        # Create test case (no model_id required)
        test_case_response = await client.post(
            "/test-cases",
            json={
                "name": "Weather query test",
                "query": "What's the weather in San Francisco?",
                "expected_mcp_server_url": test_mcp_server_url,
                "expected_tool_name": "test_tool",
                "expected_parameters": {"location": "San Francisco"},
                "available_mcp_servers": [test_mcp_server_url],
            },
        )
        assert test_case_response.status_code == 201
        test_case_id = test_case_response.json()["id"]

        # Run the test with runtime API key and model settings
        run_response = await client.post(
            f"/test-cases/{test_case_id}/run",
            headers={"X-Model-API-Key": "test-runtime-api-key"},
            json={
                "model_settings": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "timeout": 30,
                    "temperature": 0.4,
                    "max_retries": 3,
                }
            },
        )
        assert run_response.status_code == 201
        test_run_id = run_response.json()["id"]

        # Get test run status
        status_response = await client.get(f"/test-runs/{test_run_id}")
        assert status_response.status_code == 200

        test_run = status_response.json()
        assert test_run["id"] == test_run_id
        assert test_run["test_case_id"] == test_case_id
        assert test_run["status"] in ["pending", "running", "completed", "failed"]
        # Verify model_settings persisted
        assert "model_settings" in test_run
        assert test_run["model_settings"]["provider"] == "openai"
        assert test_run["model_settings"]["model"] == "gpt-4"


@pytest.mark.asyncio
async def test_multiple_tools_selection(client: AsyncClient, test_mcp_server_url: str):
    """Test tool selection with multiple available tools using runtime API key."""
    # Define tool names - tools will be loaded via mocked MCPLoaderService
    tool_names = ["search", "calculate", "get_weather"]

    # Mock MCPLoaderService for both test case creation AND test execution
    with (
        patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader_api,
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
        # Mock for test case creation
        mock_loader_api_instance = mock_loader_api.return_value
        mock_loader_api_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": name,
                    "description": f"{name} tool",
                    "input_schema": {"type": "object"},
                }
                for name in tool_names
            ]
        )

        # Mock for test execution
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": name,
                    "description": f"{name} tool",
                    "input_schema": {"type": "object"},
                }
                for name in tool_names
            ]
        )

        # Mock Pydantic AI Agent to select "search" tool
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.data = {
            "tool_name": "search",
            "parameters": {"query": "Python tutorials"},
            "reasoning": "User wants to search, selecting search tool",
            "confidence": 0.88,
        }
        mock_agent.run = AsyncMock(return_value=mock_result)

        # Create test case with all tools available (no model_id)
        test_case_response = await client.post(
            "/test-cases",
            json={
                "name": "Multi-tool test",
                "query": "Search for Python tutorials",
                "expected_mcp_server_url": test_mcp_server_url,
                "expected_tool_name": "search",
                "available_mcp_servers": [test_mcp_server_url],
            },
        )
        assert test_case_response.status_code == 201

        # Run test with runtime API key
        test_case_id = test_case_response.json()["id"]
        run_response = await client.post(
            f"/test-cases/{test_case_id}/run",
            headers={"X-Model-API-Key": "test-runtime-api-key"},
            json={
                "model_settings": {
                    "provider": "anthropic",
                    "model": "claude-3-opus",
                    "timeout": 45,
                    "temperature": 0.3,
                    "max_retries": 2,
                }
            },
        )
        assert run_response.status_code == 201


@pytest.mark.asyncio
async def test_concurrent_api_key_isolation(client: AsyncClient, test_mcp_server_url: str):
    """Test concurrent test runs with different API keys are properly isolated."""
    import asyncio

    # Mock MCPLoaderService for both test case creation AND test execution
    with (
        patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader_api,
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
        # Mock for test case creation
        mock_loader_api_instance = mock_loader_api.return_value
        mock_loader_api_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "concurrent_test_tool",
                    "description": "Tool for concurrent testing",
                    "input_schema": {"type": "object"},
                }
            ]
        )

        # Mock for test execution
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_url = AsyncMock(
            return_value=[
                {
                    "name": "concurrent_test_tool",
                    "description": "Tool for concurrent testing",
                    "input_schema": {"type": "object"},
                }
            ]
        )

        # Mock Pydantic AI Agent
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_result = MagicMock()
        mock_result.data = {
            "tool_name": "concurrent_test_tool",
            "parameters": {"test_param": "value"},
            "reasoning": "Selected concurrent_test_tool",
            "confidence": 0.9,
        }
        mock_agent.run = AsyncMock(return_value=mock_result)

        # Create a test case
        test_case_response = await client.post(
            "/test-cases",
            json={
                "name": "Concurrent API key test",
                "query": "Test concurrent execution",
                "expected_mcp_server_url": test_mcp_server_url,
                "expected_tool_name": "concurrent_test_tool",
                "available_mcp_servers": [test_mcp_server_url],
            },
        )
        assert test_case_response.status_code == 201
        test_case_id = test_case_response.json()["id"]

        # Execute 3 concurrent test runs with different API keys and models
        async def run_test_with_api_key(api_key: str, provider: str, model: str):
            return await client.post(
                f"/test-cases/{test_case_id}/run",
                headers={"X-Model-API-Key": api_key},
                json={
                    "model_settings": {
                        "provider": provider,
                        "model": model,
                        "timeout": 30,
                        "temperature": 0.5,
                        "max_retries": 3,
                    }
                },
            )

        # Execute 3 concurrent requests with different configurations
        responses = await asyncio.gather(
            run_test_with_api_key("api-key-1", "openai", "gpt-4"),
            run_test_with_api_key("api-key-2", "anthropic", "claude-3-sonnet"),
            run_test_with_api_key("api-key-3", "openai", "gpt-3.5-turbo"),
        )

        # All should succeed
        assert all(r.status_code == 201 for r in responses)

        # Extract test run IDs
        run_ids = [r.json()["id"] for r in responses]
        assert len(run_ids) == 3
        assert len(set(run_ids)) == 3  # All unique

        # Verify each test run has correct model_settings (isolated from each other)
        run_1 = await client.get(f"/test-runs/{run_ids[0]}")
        run_2 = await client.get(f"/test-runs/{run_ids[1]}")
        run_3 = await client.get(f"/test-runs/{run_ids[2]}")

        assert run_1.json()["model_settings"]["provider"] == "openai"
        assert run_1.json()["model_settings"]["model"] == "gpt-4"

        assert run_2.json()["model_settings"]["provider"] == "anthropic"
        assert run_2.json()["model_settings"]["model"] == "claude-3-sonnet"

        assert run_3.json()["model_settings"]["provider"] == "openai"
        assert run_3.json()["model_settings"]["model"] == "gpt-3.5-turbo"

        # Verify API keys are NOT in responses (security check)
        for run in [run_1, run_2, run_3]:
            assert "api_key" not in run.json().get("model_settings", {})
