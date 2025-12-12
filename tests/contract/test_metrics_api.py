"""Contract tests for metrics API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from mcp_tef.models.schemas import ToolDefinition


@pytest.fixture
async def test_runs_with_known_data(test_db):
    """Create test runs with known outcomes for metrics validation.

    Creates:
        - 2 True Positives (correct tool, correct params)
        - 1 False Positive (wrong tool selected)
        - 1 False Negative (no tool selected when one was expected)

    Note: No True Negative case due to validation constraints (expected_mcp_server_url
    must be in available_mcp_servers, which can't be satisfied for TN scenarios).

    Returns:
        dict: Contains test_case_ids, test_run_ids, and expected metrics
    """
    from unittest.mock import AsyncMock

    from mcp_tef.models.schemas import TestCaseCreate
    from mcp_tef.services.mcp_loader import MCPLoaderService
    from mcp_tef.storage.test_case_repository import TestCaseRepository
    from mcp_tef.storage.test_run_repository import TestRunRepository
    from mcp_tef.storage.tool_repository import ToolRepository

    test_case_repo = TestCaseRepository(test_db)
    test_run_repo = TestRunRepository(test_db)
    tool_repo = ToolRepository(test_db)

    server_url = "http://localhost:3000"
    test_case_ids = []
    test_run_ids = []

    # Mock MCP loader for test case creation
    mock_mcp_loader = MCPLoaderService()
    mock_mcp_loader.load_tools_from_server = AsyncMock(
        return_value=[
            ToolDefinition(
                name=f"tool_{i}", description=f"Tool {i}", input_schema={"type": "object"}
            )
            for i in range(1, 6)
        ]
    )

    # Create test cases using repository
    # Note: We only create 4 test cases (no TN case) since the validation
    # requires expected_mcp_server_url to be in available_mcp_servers, and
    # for TN cases where no tool is expected, we can't satisfy this constraint.
    # We'll simulate TN by having the LLM select no tool when one exists.
    for i in range(4):
        test_case = TestCaseCreate(
            name=f"Test case {i + 1}",
            query=f"Query {i + 1}",
            expected_mcp_server_url=server_url,
            expected_tool_name=f"tool_{i + 1}",
            expected_parameters={"param": "value"},
            available_mcp_servers=[{"url": server_url, "transport": "sse"}],
        )

        created_test_case = await test_case_repo.create(test_case, mock_mcp_loader)
        test_case_ids.append(created_test_case.id)

    # Create test runs with specific outcomes
    outcomes = [
        # TP: Correct tool and params
        {
            "test_case_id": test_case_ids[0],
            "selected_tool": "tool_1",
            "selected_params": {"param": "value"},
            "confidence_score": "robust description",  # High confidence (>=0.8)
            "classification": "TP",
            "parameter_correctness": 10.0,  # Perfect match
            "execution_time_ms": 100,
        },
        # TP: Correct tool and params
        {
            "test_case_id": test_case_ids[1],
            "selected_tool": "tool_2",
            "selected_params": {"param": "value"},
            "confidence_score": "robust description",  # High confidence (>=0.8)
            "classification": "TP",
            "parameter_correctness": 10.0,  # Perfect match
            "execution_time_ms": 150,
        },
        # FP: Wrong tool selected
        {
            "test_case_id": test_case_ids[2],
            "selected_tool": "wrong_tool",
            "selected_params": {"param": "value"},
            "confidence_score": "needs clarity",  # Medium confidence (0.5-0.8)
            "classification": "FP",
            "parameter_correctness": 0.0,
            "execution_time_ms": 200,
        },
        # FN: No tool selected when one expected
        {
            "test_case_id": test_case_ids[3],
            "selected_tool": None,
            "selected_params": None,
            "confidence_score": "misleading description",  # Low confidence (<0.5)
            "classification": "FN",
            "parameter_correctness": None,
            "execution_time_ms": 120,
        },
    ]

    for outcome in outcomes:
        # Create test run
        test_run = await test_run_repo.create(
            test_case_id=outcome["test_case_id"],
            status="pending",
        )

        # Create tool definition for selected tool (if any)
        selected_tool_id = None
        if outcome["selected_tool"]:
            from mcp_tef.models.schemas import ToolDefinitionCreate

            tool_def = ToolDefinitionCreate(
                name=outcome["selected_tool"],
                description=f"Tool {outcome['selected_tool']}",
                input_schema={"type": "object"},
                mcp_server_url=server_url,
                test_run_id=test_run.id,
            )
            created_tool = await tool_repo.create(tool_def)
            selected_tool_id = created_tool.id

        # Update test run with results
        await test_run_repo.update_status(
            test_run_id=test_run.id,
            status="completed",
            selected_tool_id=selected_tool_id,
            extracted_parameters=outcome["selected_params"],
            confidence_score=outcome["confidence_score"],
            classification=outcome["classification"],
            parameter_correctness=outcome["parameter_correctness"],
            execution_time_ms=outcome["execution_time_ms"],
        )

        test_run_ids.append(test_run.id)

    # Calculate expected metrics
    # TP=2, FP=1, FN=1, TN=0 (no TN case due to validation constraints)
    # Precision = TP/(TP+FP) = 2/3 ≈ 0.667
    # Recall = TP/(TP+FN) = 2/3 ≈ 0.667
    # F1 = 2*(P*R)/(P+R) = 2*(0.667*0.667)/(0.667+0.667) ≈ 0.667
    # Parameter accuracy: (10.0+10.0+0.0)/3 = 6.667 (FN has None, not included)
    # Avg execution time: (100+150+200+120)/4 = 142.5ms
    # Confidence distribution: 2x robust description, 1x needs clarity, 1x misleading

    return {
        "test_case_ids": test_case_ids,
        "test_run_ids": test_run_ids,
        "expected_metrics": {
            "total_tests": 4,
            "true_positives": 2,
            "false_positives": 1,
            "true_negatives": 0,
            "false_negatives": 1,
            "precision": 2 / 3,
            "recall": 2 / 3,
            "f1_score": 2 / 3,
            "parameter_accuracy": 20.0 / 3,  # (10.0+10.0+0.0)/3 ≈ 6.667
            "average_execution_time_ms": 142.5,
            "robust_description_count": 2,  # >=0.8
            "needs_clarity_count": 1,  # 0.5-0.8
            "misleading_description_count": 1,  # <0.5
        },
    }


@pytest.fixture
async def test_runs_for_filtering(test_db):
    """Create test runs for testing filter functionality.

    Creates test runs with different servers and tools for filter testing.

    Returns:
        dict: Contains IDs and metadata for filter testing
    """
    from unittest.mock import AsyncMock

    from mcp_tef.models.schemas import TestCaseCreate, ToolDefinitionCreate
    from mcp_tef.services.mcp_loader import MCPLoaderService
    from mcp_tef.storage.test_case_repository import TestCaseRepository
    from mcp_tef.storage.test_run_repository import TestRunRepository
    from mcp_tef.storage.tool_repository import ToolRepository

    test_case_repo = TestCaseRepository(test_db)
    test_run_repo = TestRunRepository(test_db)
    tool_repo = ToolRepository(test_db)

    server_url_1 = "http://localhost:3000"
    server_url_2 = "http://localhost:4000"

    # Mock MCP loader
    mock_mcp_loader = MCPLoaderService()
    mock_mcp_loader.load_tools_from_server = AsyncMock(
        side_effect=[
            [ToolDefinition(name="tool_a", description="Tool A", input_schema={"type": "object"})],
            [ToolDefinition(name="tool_b", description="Tool B", input_schema={"type": "object"})],
        ]
    )

    # Create test cases
    test_case_1 = TestCaseCreate(
        name="Test case for tool_a",
        query="Query for tool_a",
        expected_mcp_server_url=server_url_1,
        expected_tool_name="tool_a",
        expected_parameters={"param": "value"},
        available_mcp_servers=[{"url": server_url_1, "transport": "sse"}],
    )
    created_test_case_1 = await test_case_repo.create(test_case_1, mock_mcp_loader)

    test_case_2 = TestCaseCreate(
        name="Test case for tool_b",
        query="Query for tool_b",
        expected_mcp_server_url=server_url_2,
        expected_tool_name="tool_b",
        expected_parameters={"param": "value"},
        available_mcp_servers=[{"url": server_url_2, "transport": "sse"}],
    )
    created_test_case_2 = await test_case_repo.create(test_case_2, mock_mcp_loader)

    # Create test runs
    test_run_1 = await test_run_repo.create(
        test_case_id=created_test_case_1.id,
        status="pending",
    )

    # Create tool for test_run_1
    tool_1 = ToolDefinitionCreate(
        name="tool_a",
        description="Tool A",
        input_schema={"type": "object"},
        mcp_server_url=server_url_1,
        test_run_id=test_run_1.id,
    )
    created_tool_1 = await tool_repo.create(tool_1)

    # Update test_run_1 with results
    await test_run_repo.update_status(
        test_run_id=test_run_1.id,
        status="completed",
        selected_tool_id=created_tool_1.id,
        extracted_parameters={"param": "value"},
        confidence_score="robust description",
        execution_time_ms=100,
    )

    test_run_2 = await test_run_repo.create(
        test_case_id=created_test_case_2.id,
        status="pending",
    )

    # Create tool for test_run_2
    tool_2 = ToolDefinitionCreate(
        name="tool_b",
        description="Tool B",
        input_schema={"type": "object"},
        mcp_server_url=server_url_2,
        test_run_id=test_run_2.id,
    )
    created_tool_2 = await tool_repo.create(tool_2)

    # Update test_run_2 with results
    await test_run_repo.update_status(
        test_run_id=test_run_2.id,
        status="completed",
        selected_tool_id=created_tool_2.id,
        extracted_parameters={"param": "value"},
        confidence_score="robust description",
        execution_time_ms=100,
    )

    return {
        "test_case_1_id": created_test_case_1.id,
        "test_case_2_id": created_test_case_2.id,
        "test_run_1_id": test_run_1.id,
        "test_run_2_id": test_run_2.id,
        "server_url_1": server_url_1,
        "server_url_2": server_url_2,
    }


@pytest.mark.asyncio
async def test_get_metrics_summary_empty(client: AsyncClient):
    """Test GET /metrics/summary with no test runs."""
    response = await client.get("/metrics/summary")

    assert response.status_code == 200

    data = response.json()

    # Should return zero metrics when no test runs exist
    assert data["total_tests"] == 0
    assert data["true_positives"] == 0
    assert data["false_positives"] == 0
    assert data["true_negatives"] == 0
    assert data["false_negatives"] == 0
    assert data["precision"] == 0.0
    assert data["recall"] == 0.0
    assert data["f1_score"] == 0.0
    assert data["parameter_accuracy"] == 0.0
    assert data["average_execution_time_ms"] == 0.0
    assert data["robust_description_count"] == 0
    assert data["needs_clarity_count"] == 0
    assert data["misleading_description_count"] == 0
    assert data["test_run_ids"] == []


@pytest.mark.asyncio
async def test_get_metrics_summary_with_known_data(client: AsyncClient, test_runs_with_known_data):
    """Test GET /metrics/summary with known test data to verify calculations."""
    response = await client.get("/metrics/summary")
    assert response.status_code == 200

    data = response.json()
    expected = test_runs_with_known_data["expected_metrics"]

    # Verify counts
    assert data["total_tests"] == expected["total_tests"]
    assert data["true_positives"] == expected["true_positives"]
    assert data["false_positives"] == expected["false_positives"]
    assert data["true_negatives"] == expected["true_negatives"]
    assert data["false_negatives"] == expected["false_negatives"]

    # Verify calculated metrics (with tolerance for floating point)
    assert abs(data["precision"] - expected["precision"]) < 0.01
    assert abs(data["recall"] - expected["recall"]) < 0.01
    assert abs(data["f1_score"] - expected["f1_score"]) < 0.01
    assert abs(data["parameter_accuracy"] - expected["parameter_accuracy"]) < 0.1
    assert abs(data["average_execution_time_ms"] - expected["average_execution_time_ms"]) < 1.0

    # Verify confidence distribution
    assert data["robust_description_count"] == expected["robust_description_count"]
    assert data["needs_clarity_count"] == expected["needs_clarity_count"]
    assert data["misleading_description_count"] == expected["misleading_description_count"]

    # Verify test run IDs are included
    assert len(data["test_run_ids"]) == 4
    for test_run_id in test_runs_with_known_data["test_run_ids"]:
        assert test_run_id in data["test_run_ids"]


@pytest.mark.asyncio
async def test_get_metrics_summary_with_data(client: AsyncClient):
    """Test GET /metrics/summary with test run data."""
    server_url = "http://localhost:3000/sse"

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

        # Create test case
        test_case_response = await client.post(
            "/test-cases",
            json={
                "name": "Test case",
                "query": "Test query",
                "expected_mcp_server_url": server_url,
                "expected_tool_name": "test_tool",
                "expected_parameters": {"param": "value"},
                "available_mcp_servers": [{"url": server_url, "transport": "streamable-http"}],
            },
        )
        test_case_id = test_case_response.json()["id"]

    # Run test with mocks
    with (
        patch("mcp_tef.services.evaluation_service.MCPLoaderService") as mock_loader_eval,
        patch("mcp_tef.services.llm_service.Agent") as mock_agent_class,
    ):
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

    # Wait for test to complete (fire-and-forget execution)
    import asyncio

    max_polls = 50
    poll_count = 0
    status = "pending"

    while poll_count < max_polls and status not in ["completed", "failed"]:
        await asyncio.sleep(0.1)
        test_run_response = await client.get(f"/test-runs/{test_run_id}")
        status = test_run_response.json()["status"]
        poll_count += 1

    assert status == "completed", f"Test did not complete after {poll_count} polls"

    # Get metrics summary
    response = await client.get("/metrics/summary")
    assert response.status_code == 200

    data = response.json()

    # Should have at least one test
    assert data["total_tests"] >= 1

    # All fields should be present
    assert "true_positives" in data
    assert "false_positives" in data
    assert "true_negatives" in data
    assert "false_negatives" in data
    assert "precision" in data
    assert "recall" in data
    assert "f1_score" in data
    assert "parameter_accuracy" in data
    assert "average_execution_time_ms" in data
    assert "robust_description_count" in data
    assert "needs_clarity_count" in data
    assert "misleading_description_count" in data
    assert "test_run_ids" in data

    # Metrics should be valid ranges
    assert 0.0 <= data["precision"] <= 1.0
    assert 0.0 <= data["recall"] <= 1.0
    assert 0.0 <= data["f1_score"] <= 1.0
    assert 0.0 <= data["parameter_accuracy"] <= 10.0
    assert data["average_execution_time_ms"] >= 0
    assert isinstance(data["test_run_ids"], list)
    assert len(data["test_run_ids"]) >= 1


@pytest.mark.asyncio
async def test_get_metrics_summary_filter_by_test_run_id(
    client: AsyncClient, test_runs_for_filtering
):
    """Test GET /metrics/summary filtered by specific test run ID."""
    test_run_id = test_runs_for_filtering["test_run_1_id"]

    response = await client.get(
        "/metrics/summary",
        params={"test_run_id": test_run_id},
    )

    assert response.status_code == 200
    data = response.json()

    # Should only return metrics for the specific test run
    assert data["total_tests"] == 1
    assert test_run_id in data["test_run_ids"]
    assert len(data["test_run_ids"]) == 1


@pytest.mark.asyncio
async def test_get_metrics_summary_filter_by_test_case_id(
    client: AsyncClient, test_runs_for_filtering
):
    """Test GET /metrics/summary filtered by test case ID."""
    test_case_id = test_runs_for_filtering["test_case_1_id"]

    response = await client.get(
        "/metrics/summary",
        params={"test_case_id": test_case_id},
    )

    assert response.status_code == 200
    data = response.json()

    # Should only return metrics for test runs of this test case
    assert data["total_tests"] == 1
    assert test_runs_for_filtering["test_run_1_id"] in data["test_run_ids"]


@pytest.mark.asyncio
async def test_get_metrics_summary_filter_by_mcp_server_url(
    client: AsyncClient, test_runs_for_filtering
):
    """Test GET /metrics/summary filtered by MCP server URL."""
    server_url = test_runs_for_filtering["server_url_1"]

    response = await client.get(
        "/metrics/summary",
        params={"mcp_server_url": server_url},
    )

    assert response.status_code == 200
    data = response.json()

    # Should only return metrics for test runs using this server
    assert data["total_tests"] == 1
    assert test_runs_for_filtering["test_run_1_id"] in data["test_run_ids"]


@pytest.mark.asyncio
async def test_get_metrics_summary_filter_by_tool_name(
    client: AsyncClient, test_runs_for_filtering
):
    """Test GET /metrics/summary filtered by tool name."""
    response = await client.get(
        "/metrics/summary",
        params={"tool_name": "tool_a"},
    )

    assert response.status_code == 200
    data = response.json()

    # Should only return metrics for test runs using this tool
    assert data["total_tests"] == 1
    assert test_runs_for_filtering["test_run_1_id"] in data["test_run_ids"]


@pytest.mark.asyncio
async def test_get_metrics_summary_filter_by_combined_filters(
    client: AsyncClient, test_runs_for_filtering
):
    """Test GET /metrics/summary with combined server URL and tool filters."""
    response = await client.get(
        "/metrics/summary",
        params={
            "mcp_server_url": test_runs_for_filtering["server_url_1"],
            "tool_name": "tool_a",
        },
    )

    assert response.status_code == 200
    data = response.json()

    # Should match only test_run_1
    assert data["total_tests"] == 1
    assert test_runs_for_filtering["test_run_1_id"] in data["test_run_ids"]


@pytest.mark.asyncio
async def test_get_metrics_summary_with_limit(client: AsyncClient, test_runs_with_known_data):
    """Test GET /metrics/summary with limit parameter."""
    # Request only first 2 test runs
    response = await client.get(
        "/metrics/summary",
        params={"limit": 2},
    )

    assert response.status_code == 200
    data = response.json()

    # Should respect limit
    assert len(data["test_run_ids"]) <= 2
    assert data["total_tests"] <= 2


@pytest.mark.asyncio
async def test_get_metrics_summary_filter_no_matches(client: AsyncClient):
    """Test GET /metrics/summary with filter that matches no test runs."""
    response = await client.get(
        "/metrics/summary",
        params={"tool_name": "nonexistent_tool"},
    )

    assert response.status_code == 200
    data = response.json()

    # Should return empty metrics
    assert data["total_tests"] == 0
    assert len(data["test_run_ids"]) == 0
