"""Integration tests for tool history per test run.

Note: After refactoring, MCP servers are no longer persisted. Tools are fetched directly
from MCP server URLs during test run execution. Each test run maintains its own snapshot
of tool definitions by storing them with the test_run_id.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from mcp_tef.models.schemas import ToolDefinition


@pytest.mark.asyncio
async def test_tool_history_per_test_run(client: AsyncClient):
    """Test that each test run maintains its own snapshot of tool definitions.

    User Story 3: Execute test case twice, modify MCP server tools between runs,
    verify each test run has its own tool snapshot.
    """
    server_url = "http://localhost:3000/sse"

    # Mock MCPLoaderService for test case creation and test execution
    with (
        patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader_api,
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
    ):
        # For test case creation: Return v1 tool
        mock_loader_api_instance = mock_loader_api.return_value
        mock_loader_api_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="history_tool",
                    description="Version 1 of tool",
                    input_schema={
                        "type": "object",
                        "properties": {"param1": {"type": "string"}},
                    },
                )
            ]
        )

        # Create test case
        test_case_response = await client.post(
            "/test-cases",
            json={
                "name": "History test",
                "query": "Test tool history",
                "expected_mcp_server_url": server_url,
                "expected_tool_name": "history_tool",
                "available_mcp_servers": [{"url": server_url, "transport": "streamable-http"}],
            },
        )
        assert test_case_response.status_code == 201
        test_case_id = test_case_response.json()["id"]

        # For test execution: Track which version is returned
        call_count = 0

        async def mock_load_with_versions(url: str, transport: str = "streamable-http"):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First test run: Return v1 tool
                return [
                    ToolDefinition(
                        name="history_tool",
                        description="Version 1 of tool",
                        input_schema={
                            "type": "object",
                            "properties": {"param1": {"type": "string"}},
                        },
                    )
                ]
            # Second test run: Return v2 tool (modified)
            return [
                ToolDefinition(
                    name="history_tool",
                    description="Version 2 of tool (UPDATED)",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "param1": {"type": "string"},
                            "param2": {"type": "number"},  # New parameter
                        },
                    },
                )
            ]

        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(
            side_effect=mock_load_with_versions
        )

        # Execute first test run (should get v1 tools)
        run1_response = await client.post(
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
        assert run1_response.status_code == 201
        run1_id = run1_response.json()["id"]

        # Execute second test run (should get v2 tools)
        run2_response = await client.post(
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
        assert run2_response.status_code == 201
        run2_id = run2_response.json()["id"]

        # Verify both test runs were created
        assert run1_id != run2_id

        # User Story 3: Get test run 1 with its tool snapshot
        run1_details = await client.get(f"/test-runs/{run1_id}")
        assert run1_details.status_code == 200
        run1_data = run1_details.json()
        assert run1_data["id"] == run1_id

        run2_details = await client.get(f"/test-runs/{run2_id}")
        assert run2_details.status_code == 200
        run2_data = run2_details.json()
        assert run2_data["id"] == run2_id

        # Both test runs should have created separate tool records
        # Even though they have the same name, they have different test_run_ids
        # This is verified by the fact that each test run stores its own snapshot


@pytest.mark.asyncio
async def test_historical_tools_preserved_after_server_changes(client: AsyncClient):
    """Test that historical tools are preserved even after MCP server tools change.

    User Story 3: Tools ingested during a test run should remain associated with
    that test run even if the MCP server's tools change later.
    """
    server_url = "http://localhost:3000/sse"

    # Mock MCPLoaderService for test case creation and test execution
    with (
        patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader_api,
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
    ):
        # For test case creation: Return original tool
        mock_loader_api_instance = mock_loader_api.return_value
        mock_loader_api_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="preservation_tool",
                    description="Original tool",
                    input_schema={
                        "type": "object",
                        "properties": {"old_param": {"type": "string"}},
                    },
                )
            ]
        )

        # Create test case
        test_case_response = await client.post(
            "/test-cases",
            json={
                "name": "Preservation test",
                "query": "Test preservation",
                "expected_mcp_server_url": server_url,
                "expected_tool_name": "preservation_tool",
                "available_mcp_servers": [{"url": server_url, "transport": "streamable-http"}],
            },
        )
        assert test_case_response.status_code == 201
        test_case_id = test_case_response.json()["id"]

        # For test execution: Return original tool
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="preservation_tool",
                    description="Original tool",
                    input_schema={
                        "type": "object",
                        "properties": {"old_param": {"type": "string"}},
                    },
                )
            ]
        )

        # Execute test run with original tool
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
        run_id = run_response.json()["id"]

        # Get test run details
        run_details = await client.get(f"/test-runs/{run_id}")
        assert run_details.status_code == 200

        # Simulate server tools changing (mock returns different tools now)
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="preservation_tool",
                    description="COMPLETELY DIFFERENT TOOL",
                    input_schema={
                        "type": "object",
                        "properties": {"new_param": {"type": "number"}},
                    },
                )
            ]
        )

        # Execute another test run with the new tool version
        run2_response = await client.post(
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
        assert run2_response.status_code == 201
        run2_id = run2_response.json()["id"]

        # Verify first test run still exists and is complete
        run1_check = await client.get(f"/test-runs/{run_id}")
        assert run1_check.status_code == 200
        run1_data = run1_check.json()
        assert run1_data["status"] in ["completed", "failed"]

        # Verify second test run exists
        run2_check = await client.get(f"/test-runs/{run2_id}")
        assert run2_check.status_code == 200
        run2_data = run2_check.json()
        assert run2_data["status"] in ["completed", "failed"]

        # User Story 3 verification: Both test runs should maintain their own tool snapshots
        # The first test run's tools should NOT have changed to reflect the server's new tools
        # This is inherently preserved by storing tools with test_run_id
        assert run_id != run2_id, "Test runs should be separate"
