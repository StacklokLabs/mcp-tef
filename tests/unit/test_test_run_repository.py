"""Unit tests for TestRunRepository.query() method."""

import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from mcp_tef.models.schemas import (
    ModelSettingsCreate,
    TestCaseCreate,
    ToolDefinition,
    ToolDefinitionCreate,
)
from mcp_tef.storage.model_settings_repository import ModelSettingsRepository
from mcp_tef.storage.test_case_repository import TestCaseRepository
from mcp_tef.storage.test_run_repository import TestRunRepository
from mcp_tef.storage.tool_repository import ToolRepository


class TestTestRunRepositoryQuery:
    """Test TestRunRepository.query() method with various filters."""

    @pytest.fixture
    async def model_settings_id(self, test_db):
        """Create model settings and return ID."""
        repo = ModelSettingsRepository(test_db)
        model_settings_data = ModelSettingsCreate(
            provider="openai",
            model="gpt-4",
            timeout=30,
            temperature=0.7,
            max_retries=3,
            base_url="https://api.openai.com/v1",
            system_prompt="You are a helpful assistant",
        )
        settings = await repo.create(model_settings_data)
        return settings.id

    @pytest.fixture
    async def test_case_id(self, test_db):
        """Create test case and return ID."""
        repo = TestCaseRepository(test_db)
        mock_loader = AsyncMock()
        # Mock must return tools that include the expected tool
        mock_loader.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="get_weather",
                    description="Get current weather",
                    input_schema={"type": "object"},
                )
            ]
        )

        test_case_data = TestCaseCreate(
            name="Test Case 1",
            query="What is the weather?",
            expected_tool_calls=[
                {
                    "mcp_server_url": "http://localhost:3000",
                    "tool_name": "get_weather",
                    "parameters": {"location": "San Francisco"},
                }
            ],
            available_mcp_servers=[
                {"url": "http://localhost:3000", "transport": "streamable-http"}
            ],
        )
        test_case = await repo.create(test_case_data, mock_loader)
        return test_case.id

    @pytest.fixture
    async def test_case_id_2(self, test_db):
        """Create second test case and return ID."""
        repo = TestCaseRepository(test_db)
        mock_loader = AsyncMock()
        # Mock must return tools that include the expected tool
        mock_loader.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="get_events",
                    description="Get calendar events",
                    input_schema={"type": "object"},
                )
            ]
        )

        test_case_data = TestCaseCreate(
            name="Test Case 2",
            query="Get calendar events",
            expected_tool_calls=[
                {
                    "mcp_server_url": "http://localhost:4000",
                    "tool_name": "get_events",
                    "parameters": {"date": "2025-01-01"},
                }
            ],
            available_mcp_servers=[
                {"url": "http://localhost:4000", "transport": "streamable-http"}
            ],
        )
        test_case = await repo.create(test_case_data, mock_loader)
        return test_case.id

    @pytest.fixture
    async def test_run_id_1(self, test_db, test_case_id, model_settings_id):
        """Create first test run and return ID."""
        repo = TestRunRepository(test_db)
        test_run = await repo.create(
            test_case_id=test_case_id,
            model_settings_id=model_settings_id,
            status="completed",
        )
        return test_run.id

    @pytest.fixture
    async def test_run_id_2(self, test_db, test_case_id_2, model_settings_id):
        """Create second test run and return ID."""
        repo = TestRunRepository(test_db)
        test_run = await repo.create(
            test_case_id=test_case_id_2,
            model_settings_id=model_settings_id,
            status="completed",
        )
        return test_run.id

    @pytest.fixture
    async def weather_tool_id(self, test_db, test_run_id_1):
        """Create weather tool and return ID."""
        repo = ToolRepository(test_db)
        tool_data = ToolDefinitionCreate(
            name="get_weather",
            description="Get current weather",
            input_schema={"type": "object", "properties": {"location": {"type": "string"}}},
            mcp_server_url="http://localhost:3000",
            test_run_id=test_run_id_1,
        )
        tool = await repo.create(tool_data)
        return tool.id

    @pytest.fixture
    async def calendar_tool_id(self, test_db, test_run_id_2):
        """Create calendar tool and return ID."""
        repo = ToolRepository(test_db)
        tool_data = ToolDefinitionCreate(
            name="get_events",
            description="Get calendar events",
            input_schema={"type": "object", "properties": {"date": {"type": "string"}}},
            mcp_server_url="http://localhost:4000",
            test_run_id=test_run_id_2,
        )
        tool = await repo.create(tool_data)
        return tool.id

    async def test_query_all_test_runs(self, test_db, test_run_id_1, test_run_id_2):
        """Test querying all test runs without filters."""
        repo = TestRunRepository(test_db)

        results = await repo.query()

        assert len(results) == 2
        assert {r.id for r in results} == {test_run_id_1, test_run_id_2}

        # Verify results are ordered by created_at DESC (most recent first)
        assert results[0].created_at >= results[1].created_at

    async def test_query_by_test_run_id(self, test_db, test_run_id_1):
        """Test querying by specific test run ID."""
        repo = TestRunRepository(test_db)

        results = await repo.query(test_run_id=test_run_id_1)

        assert len(results) == 1
        assert results[0].id == test_run_id_1
        assert results[0].status == "completed"
        assert results[0].model_settings is not None
        assert results[0].model_settings.provider == "openai"

    async def test_query_by_test_case_id(self, test_db, test_case_id, test_run_id_1):
        """Test querying by test case ID."""
        repo = TestRunRepository(test_db)

        results = await repo.query(test_case_id=test_case_id)

        assert len(results) == 1
        assert results[0].id == test_run_id_1
        assert results[0].test_case_id == test_case_id

    async def test_query_by_mcp_server_url(self, test_db, test_run_id_1, weather_tool_id):
        """Test querying by MCP server URL."""
        repo = TestRunRepository(test_db)
        results = await repo.query(mcp_server_url="http://localhost:3000")

        assert len(results) == 1
        assert results[0].id == test_run_id_1

    async def test_query_by_tool_name(self, test_db, test_run_id_2, calendar_tool_id):
        """Test querying by tool name."""
        repo = TestRunRepository(test_db)
        results = await repo.query(tool_name="get_events")

        assert len(results) == 1
        assert results[0].id == test_run_id_2

    async def test_query_by_tool_name_and_mcp_server_url(
        self, test_db, test_run_id_1, weather_tool_id
    ):
        """Test querying by both tool name and MCP server URL."""
        repo = TestRunRepository(test_db)
        results = await repo.query(tool_name="get_weather", mcp_server_url="http://localhost:3000")

        assert len(results) == 1
        assert results[0].id == test_run_id_1

    async def test_query_returns_empty_list_when_no_matches(self, test_db):
        """Test that query returns empty list when no test runs match filters."""
        repo = TestRunRepository(test_db)

        results = await repo.query(test_case_id="nonexistent-id")

        assert results == []

    async def test_query_with_pagination(self, test_db, model_settings_id):
        """Test query pagination with offset and limit."""
        repo = TestCaseRepository(test_db)
        mock_loader = AsyncMock()
        mock_loader.load_tools_from_server = AsyncMock(
            return_value=[
                ToolDefinition(
                    name="test_tool",
                    description="Test tool",
                    input_schema={"type": "object"},
                )
            ]
        )

        # Create a new test case specifically for this test
        test_case_data = TestCaseCreate(
            name="Pagination Test Case",
            query="Test pagination",
            expected_tool_calls=[
                {
                    "mcp_server_url": "http://localhost:5000",
                    "tool_name": "test_tool",
                    "parameters": {},
                }
            ],
            available_mcp_servers=[
                {"url": "http://localhost:5000", "transport": "streamable-http"}
            ],
        )
        test_case = await repo.create(test_case_data, mock_loader)

        # Create 5 test runs for this test case
        test_run_repo = TestRunRepository(test_db)
        test_run_ids = []
        for _ in range(5):
            test_run = await test_run_repo.create(
                test_case_id=test_case.id,
                model_settings_id=model_settings_id,
                status="completed",
            )
            test_run_ids.append(test_run.id)

        # Test first page (limit=2)
        page_1 = await test_run_repo.query(test_case_id=test_case.id, limit=2, offset=0)
        assert len(page_1) == 2

        # Test second page (limit=2, offset=2)
        page_2 = await test_run_repo.query(test_case_id=test_case.id, limit=2, offset=2)
        assert len(page_2) == 2

        # Test third page (limit=2, offset=4)
        page_3 = await test_run_repo.query(test_case_id=test_case.id, limit=2, offset=4)
        assert len(page_3) == 1

        # Verify no overlap between pages
        page_1_ids = {r.id for r in page_1}
        page_2_ids = {r.id for r in page_2}
        page_3_ids = {r.id for r in page_3}
        assert page_1_ids.isdisjoint(page_2_ids)
        assert page_1_ids.isdisjoint(page_3_ids)
        assert page_2_ids.isdisjoint(page_3_ids)

    async def test_query_includes_model_settings(self, test_db, test_run_id_1):
        """Test that query results include complete model settings."""
        repo = TestRunRepository(test_db)

        results = await repo.query(test_run_id=test_run_id_1)

        assert len(results) == 1
        model_settings = results[0].model_settings
        assert model_settings is not None
        assert model_settings.provider == "openai"
        assert model_settings.model == "gpt-4"
        assert model_settings.timeout == 30
        assert model_settings.temperature == 0.7
        assert model_settings.max_retries == 3
        assert model_settings.base_url == "https://api.openai.com/v1"
        assert model_settings.system_prompt == "You are a helpful assistant"
        assert isinstance(model_settings.created_at, datetime)

    async def test_query_includes_all_tools(self, test_db, test_run_id_1, weather_tool_id):
        """Test that query results include all tools available in test run."""
        # Create additional tools for the same test run
        tool_repo = ToolRepository(test_db)
        await tool_repo.create(
            ToolDefinitionCreate(
                name="get_forecast",
                description="Get weather forecast",
                input_schema={"type": "object"},
                mcp_server_url="http://localhost:3000",
                test_run_id=test_run_id_1,
            )
        )
        await tool_repo.create(
            ToolDefinitionCreate(
                name="get_alerts",
                description="Get weather alerts",
                input_schema={"type": "object"},
                mcp_server_url="http://localhost:3000",
                test_run_id=test_run_id_1,
            )
        )

        repo = TestRunRepository(test_db)
        results = await repo.query(test_run_id=test_run_id_1)

        assert len(results) == 1
        tools = results[0].tools
        assert len(tools) == 3  # get_weather, get_forecast, get_alerts
        tool_names = {t.name for t in tools}
        assert tool_names == {"get_weather", "get_forecast", "get_alerts"}

    async def test_query_handles_null_model_settings(self, test_db, test_case_id):
        """Test that query handles test runs without model settings (NULL FK)."""
        repo = TestRunRepository(test_db)

        # Create test run without model_settings_id
        test_run = await repo.create(
            test_case_id=test_case_id,
            model_settings_id=None,
            status="pending",
        )

        results = await repo.query(test_run_id=test_run.id)

        assert len(results) == 1
        assert results[0].model_settings is None
        assert results[0].status == "pending"

    async def test_query_with_all_test_run_fields(self, test_db, test_run_id_1, weather_tool_id):
        """Test that query returns all test run fields correctly."""
        # Update test run with all optional fields
        await test_db.execute(
            """UPDATE test_runs SET
               llm_confidence = ?,
               avg_parameter_correctness = ?,
               confidence_score = ?,
               classification = ?,
               execution_time_ms = ?,
               error_message = ?,
               llm_response_raw = ?,
               completed_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (
                "high",
                9.5,
                "robust description",
                "TP",
                1250,
                None,
                json.dumps({"result": "success"}),
                test_run_id_1,
            ),
        )
        await test_db.commit()

        repo = TestRunRepository(test_db)
        results = await repo.query(test_run_id=test_run_id_1)

        assert len(results) == 1
        tr = results[0]
        assert tr.llm_confidence == "high"
        assert tr.avg_parameter_correctness == 9.5
        assert tr.confidence_score == "robust description"
        assert tr.classification == "TP"
        assert tr.execution_time_ms == 1250
        assert tr.error_message is None
        assert tr.llm_response_raw == json.dumps({"result": "success"})
        assert tr.completed_at is not None

    async def test_query_multiple_filters_combined(
        self, test_db, test_case_id, test_run_id_1, weather_tool_id
    ):
        """Test combining multiple query filters."""
        repo = TestRunRepository(test_db)

        # Query with test_case_id + mcp_server_url
        results = await repo.query(
            test_case_id=test_case_id, mcp_server_url="http://localhost:3000"
        )

        assert len(results) == 1
        assert results[0].id == test_run_id_1
        assert results[0].test_case_id == test_case_id

    async def test_query_ordering_by_created_at_desc(
        self, test_db, test_case_id, model_settings_id
    ):
        """Test that results are ordered by created_at DESC (most recent first)."""
        import asyncio

        repo = TestRunRepository(test_db)

        # Create test runs with small delays to ensure different timestamps
        test_run_ids = []
        for _ in range(3):
            test_run = await repo.create(
                test_case_id=test_case_id,
                model_settings_id=model_settings_id,
                status="completed",
            )
            test_run_ids.append(test_run.id)
            await asyncio.sleep(0.01)  # 10ms delay

        results = await repo.query()

        # Verify ordering: most recent first
        assert len(results) >= 3
        for i in range(len(results) - 1):
            assert results[i].created_at >= results[i + 1].created_at
