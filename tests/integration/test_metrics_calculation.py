"""Integration tests for metrics calculation across multiple test runs."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from mcp_tef.models.schemas import ToolDefinition
from tests.conftest import wait_for_test_run_completion


@pytest.mark.asyncio
async def test_metrics_precision_recall_calculation(
    client: AsyncClient,
    test_mcp_server_url: str,
):
    """Test that precision, recall, and F1 are correctly calculated."""
    # Mock MCPLoaderService for both test case creation AND test execution
    with (
        patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader_api,
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
        # Mock for test case creation (API layer)
        mock_loader_api_instance = mock_loader_api.return_value
        mock_loader_api_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="test_tool",
                    description="Test tool",
                    input_schema={"type": "object", "properties": {}},
                ),
                ToolDefinition(
                    name="tool_wrong",
                    description="Wrong tool",
                    input_schema={"type": "object", "properties": {}},
                ),
            ]
        )

        # Mock for test execution (EvaluationService layer)
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="test_tool",
                    description="Test tool",
                    input_schema={"type": "object", "properties": {}},
                ),
                ToolDefinition(
                    name="tool_wrong",
                    description="Wrong tool",
                    input_schema={"type": "object", "properties": {}},
                ),
            ]
        )

        # Create multiple test cases with known outcomes
        # Case 1: True Positive (expect test_tool, LLM should select test_tool)
        tc1_response = await client.post(
            "/test-cases",
            json={
                "name": "TP case - test_tool",
                "query": "Select test_tool",
                "expected_mcp_server_url": test_mcp_server_url,
                "expected_tool_name": "test_tool",
                "available_mcp_servers": [
                    {"url": test_mcp_server_url, "transport": "streamable-http"}
                ],
            },
        )
        assert tc1_response.status_code == 201
        tc1_id = tc1_response.json()["id"]

        # Case 2: False Positive candidate (expect tool_wrong, but LLM might select test_tool)
        tc2_response = await client.post(
            "/test-cases",
            json={
                "name": "Case with wrong tool",
                "query": "Select tool_wrong",
                "expected_mcp_server_url": test_mcp_server_url,
                "expected_tool_name": "tool_wrong",
                "available_mcp_servers": [
                    {"url": test_mcp_server_url, "transport": "streamable-http"}
                ],
            },
        )
        assert tc2_response.status_code == 201
        tc2_id = tc2_response.json()["id"]

        # Mock Agent to select test_tool for first test
        mock_agent1 = MagicMock()
        mock_result1 = MagicMock()
        mock_result1.data = {
            "tool_name": "test_tool",
            "parameters": {},
            "reasoning": "Selected test_tool",
            "confidence": 0.85,
        }
        mock_agent1.run = AsyncMock(return_value=mock_result1)

        mock_agent_class.return_value = mock_agent1
        run1 = await client.post(
            f"/test-cases/{tc1_id}/run",
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
        assert run1.status_code == 201
        test_run_id1 = run1.json()["id"]

        # Mock Agent to select tool_wrong for second test
        mock_agent2 = MagicMock()
        mock_result2 = MagicMock()
        mock_result2.data = {
            "tool_name": "tool_wrong",
            "parameters": {},
            "reasoning": "Selected tool_wrong",
            "confidence": 0.85,
        }
        mock_agent2.run = AsyncMock(return_value=mock_result2)

        mock_agent_class.return_value = mock_agent2
        run2 = await client.post(
            f"/test-cases/{tc2_id}/run",
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
        assert run2.status_code == 201
        test_run_id2 = run2.json()["id"]

        # Wait for both tests to complete (fire-and-forget execution)
        status1 = await wait_for_test_run_completion(client, test_run_id1)
        status2 = await wait_for_test_run_completion(client, test_run_id2)
        assert status1 == "completed"
        assert status2 == "completed"

        # Get metrics summary
        response = await client.get("/metrics/summary")
        assert response.status_code == 200

        metrics = response.json()

        # Should have 2 total tests (the 2 created in this test)
        assert metrics["total_tests"] == 2

        # Verify all classification fields exist
        assert "true_positives" in metrics
        assert "false_positives" in metrics
        assert "true_negatives" in metrics
        assert "false_negatives" in metrics

        # Verify metrics exist and are in valid range
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1_score" in metrics
        assert 0.0 <= metrics["precision"] <= 1.0
        assert 0.0 <= metrics["recall"] <= 1.0
        assert 0.0 <= metrics["f1_score"] <= 1.0


@pytest.mark.asyncio
async def test_metrics_parameter_accuracy_calculation(
    client: AsyncClient, test_mcp_server_url: str
):
    """Test that parameter accuracy is correctly calculated."""
    # Mock MCPLoaderService for both test case creation AND test execution
    with (
        patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader_api,
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
        # Mock for test case creation (API layer)
        mock_loader_api_instance = mock_loader_api.return_value
        mock_loader_api_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="param_tool",
                    description="Tool with params",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "arg1": {"type": "string"},
                            "arg2": {"type": "number"},
                        },
                        "required": ["arg1", "arg2"],
                    },
                )
            ]
        )

        # Mock for test execution (EvaluationService layer)
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="param_tool",
                    description="Tool with params",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "arg1": {"type": "string"},
                            "arg2": {"type": "number"},
                        },
                        "required": ["arg1", "arg2"],
                    },
                )
            ]
        )

        # Create test case with expected parameters
        tc_response = await client.post(
            "/test-cases",
            json={
                "name": "Parameter test",
                "query": "Execute with arg1=hello and arg2=42",
                "expected_mcp_server_url": test_mcp_server_url,
                "expected_tool_name": "param_tool",
                "expected_parameters": {"arg1": "hello", "arg2": 42},
                "available_mcp_servers": [
                    {"url": test_mcp_server_url, "transport": "streamable-http"}
                ],
            },
        )
        assert tc_response.status_code == 201
        tc_id = tc_response.json()["id"]

        # Mock Agent to select param_tool with correct parameters
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {
            "tool_name": "param_tool",
            "parameters": {"arg1": "hello", "arg2": 42},
            "reasoning": "Selected param_tool with correct parameters",
            "confidence": 0.85,
        }
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_agent_class.return_value = mock_agent

        run_response = await client.post(
            f"/test-cases/{tc_id}/run",
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
        assert run_response.status_code == 201
        test_run_id = run_response.json()["id"]

        # Wait for test completion (fire-and-forget execution)
        status = await wait_for_test_run_completion(client, test_run_id)
        assert status == "completed"

        # Get metrics
        response = await client.get("/metrics/summary")
        assert response.status_code == 200

        metrics = response.json()

        # Parameter accuracy should be present (0-10 scale)
        assert "parameter_accuracy" in metrics
        assert 0.0 <= metrics["parameter_accuracy"] <= 10.0


@pytest.mark.asyncio
async def test_metrics_execution_time_average(client: AsyncClient, test_mcp_server_url: str):
    """Test that average execution time is calculated."""
    # Mock MCPLoaderService for both test case creation AND test execution
    with (
        patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader_api,
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
        # Mock for test case creation (API layer)
        mock_loader_api_instance = mock_loader_api.return_value
        mock_loader_api_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="test_tool",
                    description="Test tool",
                    input_schema={"type": "object", "properties": {"param": {"type": "string"}}},
                )
            ]
        )

        # Mock for test execution (EvaluationService layer)
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="test_tool",
                    description="Test tool",
                    input_schema={"type": "object", "properties": {"param": {"type": "string"}}},
                )
            ]
        )

        # Create and run test case
        tc_response = await client.post(
            "/test-cases",
            json={
                "name": "Timing test",
                "query": "Test execution time",
                "expected_mcp_server_url": test_mcp_server_url,
                "expected_tool_name": "test_tool",
                "available_mcp_servers": [
                    {"url": test_mcp_server_url, "transport": "streamable-http"}
                ],
            },
        )
        assert tc_response.status_code == 201
        tc_id = tc_response.json()["id"]

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
            f"/test-cases/{tc_id}/run",
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
        assert run_response.status_code == 201
        test_run_id = run_response.json()["id"]

        # Wait for test completion
        status = await wait_for_test_run_completion(client, test_run_id)
        assert status == "completed"

        # Get metrics
        response = await client.get("/metrics/summary")
        assert response.status_code == 200

        metrics = response.json()

        # Should have average execution time
        assert "average_execution_time_ms" in metrics
        assert metrics["average_execution_time_ms"] > 0


@pytest.mark.asyncio
async def test_metrics_confidence_distribution(client: AsyncClient, test_mcp_server_url: str):
    """Test confidence distribution calculation."""
    # Mock MCPLoaderService for both test case creation AND test execution
    with (
        patch("mcp_tef.api.test_cases.MCPLoaderService") as mock_loader_api,
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
        # Mock for test case creation (API layer)
        mock_loader_api_instance = mock_loader_api.return_value
        mock_loader_api_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="test_tool",
                    description="Test tool",
                    input_schema={"type": "object", "properties": {"param": {"type": "string"}}},
                )
            ]
        )

        # Mock for test execution (EvaluationService layer)
        mock_loader_eval_instance = mock_loader_eval.return_value
        mock_loader_eval_instance.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="test_tool",
                    description="Test tool",
                    input_schema={"type": "object", "properties": {"param": {"type": "string"}}},
                )
            ]
        )

        # Create and run test case
        tc_response = await client.post(
            "/test-cases",
            json={
                "name": "Confidence test",
                "query": "Test confidence scoring",
                "expected_mcp_server_url": test_mcp_server_url,
                "expected_tool_name": "test_tool",
                "available_mcp_servers": [
                    {"url": test_mcp_server_url, "transport": "streamable-http"}
                ],
            },
        )
        assert tc_response.status_code == 201
        tc_id = tc_response.json()["id"]

        # Mock Agent
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
            f"/test-cases/{tc_id}/run",
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
        assert run_response.status_code == 201
        test_run_id = run_response.json()["id"]

        # Wait for test completion
        status = await wait_for_test_run_completion(client, test_run_id)
        assert status == "completed"

        # Get metrics
        response = await client.get("/metrics/summary")
        assert response.status_code == 200

        metrics = response.json()

        # Should have confidence score counts
        assert "robust_description_count" in metrics
        assert "needs_clarity_count" in metrics
        assert "misleading_description_count" in metrics
        assert isinstance(metrics["robust_description_count"], int)
        assert isinstance(metrics["needs_clarity_count"], int)
        assert isinstance(metrics["misleading_description_count"], int)


@pytest.mark.asyncio
async def test_metrics_division_by_zero_handling(client: AsyncClient):
    """Test that division by zero is handled gracefully."""
    # Get metrics with no test runs
    response = await client.get("/metrics/summary")
    assert response.status_code == 200

    metrics = response.json()

    # Should return 0.0 for all metrics when no data
    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["f1_score"] == 0.0
    assert metrics["parameter_accuracy"] == 0.0
    assert metrics["average_execution_time_ms"] == 0.0
