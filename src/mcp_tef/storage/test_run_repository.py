"""Repository for test run database operations."""

import json
from datetime import datetime
from sqlite3 import Row
from uuid import uuid4

import aiosqlite
import structlog

from mcp_tef.api.errors import DatabaseError, ResourceNotFoundError
from mcp_tef.models.schemas import (
    ModelSettingsResponse,
    TestRunResponse,
    ToolEnrichedResponse,
)

logger = structlog.get_logger(__name__)


class TestRunRepository:
    """Repository for managing test runs in SQLite."""

    def __init__(self, db: aiosqlite.Connection):
        """Initialize repository with database connection.

        Args:
            db: Active aiosqlite connection
        """
        self.db = db

    async def create(
        self,
        test_case_id: str,
        model_settings_id: str | None = None,
        status: str = "pending",
        error_message: str | None = None,
        execution_time_ms: int | None = None,
    ) -> TestRunResponse:
        """Create a new test run.

        Args:
            test_case_id: Test case ID to run
            model_settings_id: Model settings ID (optional)
            status: Initial status (default: 'pending')
            error_message: Error message for failed status (optional)
            execution_time_ms: Execution time in milliseconds (optional)

        Returns:
            Created test run

        Raises:
            ResourceNotFoundError: If test case not found
            DatabaseError: If database operation fails
        """
        test_run_id = str(uuid4())

        try:
            # Build insert query dynamically based on provided fields
            fields = ["id", "test_case_id", "model_settings_id", "status"]
            placeholders = ["?", "?", "?", "?"]
            values: list = [test_run_id, test_case_id, model_settings_id, status]

            if error_message is not None:
                fields.append("error_message")
                placeholders.append("?")
                values.append(error_message)

            if execution_time_ms is not None:
                fields.append("execution_time_ms")
                placeholders.append("?")
                values.append(execution_time_ms)

            if status in ["completed", "failed"]:
                fields.append("completed_at")
                placeholders.append("CURRENT_TIMESTAMP")

            query = f"""
                INSERT INTO test_runs ({", ".join(fields)})
                VALUES ({", ".join(placeholders)})
            """  # nosec: "B608" Safe: fields/placeholders are internally controlled, values parameterized

            await self.db.execute(query, tuple(values))
            await self.db.commit()

            logger.info(
                f"Created test run: {test_run_id} for test case {test_case_id} "
                f"(model_settings_id: {model_settings_id}, status: {status})"
            )

            return await self.get(test_run_id)

        except aiosqlite.IntegrityError as e:
            # Check if it's a foreign key constraint violation
            if "FOREIGN KEY constraint failed" in str(e):
                logger.error(f"Test case not found: {test_case_id}")
                raise ResourceNotFoundError("TestCase", test_case_id) from e
            logger.error(f"Failed to create test run: {e}")
            raise DatabaseError(f"Failed to create test run: {str(e)}", e) from e
        except Exception as e:
            logger.error(f"Failed to create test run: {e}")
            raise DatabaseError(f"Failed to create test run: {str(e)}", e) from e

    async def get(self, test_run_id: str) -> TestRunResponse:
        """Get a test run by ID with model settings and enriched tool data.

        Args:
            test_run_id: Test run ID

        Returns:
            Test run with model_settings, enriched tools, and expected tool

        Raises:
            ResourceNotFoundError: If test run not found
            DatabaseError: If database operation fails
        """
        results = await self.query(test_run_id=test_run_id, limit=1)
        if not results:
            raise ResourceNotFoundError("TestRun", test_run_id)
        return results[0]

    async def query(
        self,
        test_run_id: str | None = None,
        test_case_id: str | None = None,
        mcp_server_url: str | None = None,
        tool_name: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[TestRunResponse]:
        """Query test runs with optional filters.

        Args:
            test_run_id: Optional test run ID filter
            test_case_id: Optional test case ID filter
            mcp_server_url: Optional MCP server URL filter
            tool_name: Optional tool name filter
            status: Optional status filter (e.g., 'completed', 'pending', 'failed')
            offset: Pagination offset (default: 0)
            limit: Pagination limit (default: 100)

        Returns:
            List of TestRunResponse objects matching the filters

        Raises:
            DatabaseError: If database operation fails
        """
        query, args = self._build_test_run_query(
            test_run_id=test_run_id,
            test_case_id=test_case_id,
            mcp_server_url=mcp_server_url,
            tool_name=tool_name,
            status=status,
            offset=offset,
            limit=limit,
        )

        try:
            cursor = await self.db.execute(query, args)
            rows = await cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to query test runs: {e}")
            raise DatabaseError(f"Failed to query test runs: {str(e)}", e) from e

        if not rows:
            return []

        results: list[TestRunResponse] = []
        for row in rows:
            result = await self._build_test_run_response(row)
            results.append(result)
        return results

    def _build_test_run_query(
        self,
        test_run_id: str | None = None,
        test_case_id: str | None = None,
        mcp_server_url: str | None = None,
        tool_name: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[str, tuple]:
        """Build SQL query and args for retrieving test runs with joined data.

        Supports the following API patterns:
        - GET /test-runs - List all test runs
        - GET /test-runs?test_case_id={id} - Filter by test case
        - GET /test-runs?mcp_server_url={url} - Filter by MCP server URL
        - GET /test-runs?tool_name={name}&mcp_server_url={url} - Filter by tool
        - GET /test-runs?status={status} - Filter by status

        Args:
            test_run_id: Optional test run ID filter
            test_case_id: Optional test case ID filter
            mcp_server_url: Optional MCP server URL filter
            tool_name: Optional tool name filter
            status: Optional status filter (e.g., 'completed', 'pending', 'failed')
            offset: Pagination offset (default: 0)
            limit: Pagination limit (default: 100)

        Returns:
            Tuple of (query_string, args_tuple)

        Notes:
            - Query joins test_runs with model_settings and test_cases
            - Returns all fields needed to construct TestRunResponse
            - Results ordered by created_at DESC for most recent first
            - Leverages idx_test_run_test_case when filtering by test_case_id
        """
        args = []
        test_runs = "test_runs"
        if test_run_id or status:
            where_clause = " AND ".join(
                [
                    clause
                    for clause in [
                        "id = ?" if test_run_id else None,
                        "status = ?" if status else None,
                    ]
                    if clause
                ]
            )
            test_runs = f"""(
    SELECT *
    FROM test_runs
    WHERE {where_clause}
)"""  # nosec: "B608" Safe: where_clause built from controlled conditions, values parameterized
            if test_run_id:
                args.append(test_run_id)
            if status:
                args.append(status)

        model_settings = "model_settings"

        test_cases = "test_cases"
        if test_case_id:
            test_cases = """(
    SELECT *
    FROM test_cases
    WHERE id = ?
)"""
            args.append(test_case_id)

        tools = "tool_definitions"
        if tool_name:
            tools = f"""(
    WITH test_run_ids AS (
        SELECT test_run_id
        FROM tool_definitions
        WHERE name = ?{" AND mcp_server_url = ?" if mcp_server_url else ""}
    )
    SELECT *
    FROM tool_definitions
    INNER JOIN test_run_ids trids ON trids.test_run_id = tool_definitions.test_run_id
)"""  # nosec: "B608" Safe: conditional clause is controlled, values parameterized
            args.append(tool_name)
            if mcp_server_url:
                args.append(mcp_server_url)

        join_test_case_mcp_servers = ""
        if mcp_server_url:
            test_case_mcp_servers = """(
    WITH test_case_ids AS (
        SELECT test_case_id
        FROM test_case_mcp_servers
        WHERE mcp_server_url = ?
    )
    SELECT *
    FROM test_case_mcp_servers
    INNER JOIN test_case_ids tcids ON tcids.test_case_id = test_case_mcp_servers.test_case_id
)"""
            join_test_case_mcp_servers = (
                f"INNER JOIN {test_case_mcp_servers} mcps ON mcps.test_case_id = tc.id"
            )
            args.append(mcp_server_url)

        args.extend([limit, offset])
        query = f"""
SELECT
    tr.id,
    tr.test_case_id,
    tr.model_settings_id,
    tr.status,
    tr.llm_response_raw,
    tr.selected_tool_id,
    tr.extracted_parameters,
    tr.llm_confidence,
    tr.parameter_correctness,
    tr.confidence_score,
    tr.classification,
    tr.execution_time_ms,
    tr.error_message,
    tr.created_at,
    tr.completed_at,
    -- Model settings fields
    ms.id,
    ms.provider,
    ms.model,
    ms.timeout,
    ms.temperature,
    ms.max_retries,
    ms.base_url,
    ms.system_prompt,
    ms.created_at,
    -- Test case expected tool fields
    tc.expected_mcp_server_url,
    tc.expected_tool_name,
    tc.expected_parameters,
    -- Aggregates
    json_group_array(COALESCE(td.id, '')) AS td_ids,
    json_group_array(COALESCE(td.name, '')) AS td_names,
    json_group_array(COALESCE(td.mcp_server_url, '')) AS td_mcp_server_urls,
    json_group_array(COALESCE(td.input_schema, '')) AS td_input_schemas
FROM {test_runs} tr
LEFT JOIN {model_settings} ms ON tr.model_settings_id = ms.id
{"INNER" if test_case_id else "LEFT"} JOIN {test_cases} tc ON tr.test_case_id = tc.id
{"INNER" if tool_name else "LEFT"} JOIN {tools} td ON td.test_run_id = tr.id
{join_test_case_mcp_servers}
GROUP BY {", ".join([str(i) for i in range(1, 27)])}
ORDER BY tr.created_at DESC
LIMIT ? OFFSET ?
"""  # nosec: "B608" Safe: updates list is internally controlled, values parameterized

        return query, tuple(args)

    async def _build_test_run_response(self, row: Row) -> TestRunResponse:
        """Build TestRunResponse from database row.

        Maps row indices from _build_test_run_query to TestRunResponse fields.

        Row structure (from _build_test_run_query):
        (test run)
        [0]  tr.id
        [1]  tr.test_case_id
        [2]  tr.model_settings_id
        [3]  tr.status
        [4]  tr.llm_response_raw
        [5]  tr.selected_tool_id
        [6]  tr.extracted_parameters
        [7]  tr.llm_confidence
        [8]  tr.parameter_correctness
        [9]  tr.confidence_score
        [10] tr.classification
        [11] tr.execution_time_ms
        [12] tr.error_message
        [13] tr.created_at
        [14] tr.completed_at
        (model_settings)
        [15] ms.id
        [16] ms.provider
        [17] ms.model
        [18] ms.timeout
        [19] ms.temperature
        [20] ms.max_retries
        [21] ms.base_url
        [22] ms.system_prompt
        [23] ms.created_at
        (test case)
        [24] tc.expected_mcp_server_url
        [25] tc.expected_tool_name
        [26] tc.expected_parameters
        (tools aggregate)
        [27] td_ids
        [28] td_names
        [29] td_mcp_server_urls
        [30] td_input_schemas

        Args:
            row: Database row from query

        Returns:
            Constructed TestRunResponse object
        """
        # Parse basic test run fields
        tools: list[ToolEnrichedResponse] = []
        if row[27] and row[27] != "None":
            tool_ids = json.loads(row[27])
            tool_names = json.loads(row[28])
            tool_mcp_server_urls = json.loads(row[29])
            tool_input_schemas = json.loads(row[30])
            for (
                tool_definition_id,
                tool_name,
                tool_mcp_server_url,
                tool_input_schema,
            ) in zip(tool_ids, tool_names, tool_mcp_server_urls, tool_input_schemas, strict=False):
                tools.append(
                    ToolEnrichedResponse(
                        id=tool_definition_id,
                        name=tool_name,
                        mcp_server_url=tool_mcp_server_url,
                        parameters=json.loads(tool_input_schema)
                        if tool_input_schema.strip() and tool_input_schema != "None"
                        else None,
                    )
                )

        test_run_id = row[0]
        test_case_id = row[1]
        extracted_parameters = json.loads(row[6]) if row[6] else None

        # Build model_settings if present (LEFT JOIN, so may be NULL)
        model_settings = None
        if row[15]:  # ms.id is not NULL
            model_settings = ModelSettingsResponse(
                id=row[15],
                provider=row[16],
                model=row[17],
                timeout=row[18],
                temperature=row[19],
                max_retries=row[20],
                base_url=row[21],
                system_prompt=row[22],
                created_at=datetime.fromisoformat(row[23]),
            )

        # Get selected_tool enriched data if present

        selected_tool = None
        if row[5]:  # selected_tool_id is not NULL
            matching_tools = [t for t in tools if t.id == row[5]]
            if not matching_tools:
                logger.warn("Could not find selected_tool", selected_tool_name=row[5])
            else:
                selected_tool = ToolEnrichedResponse(
                    id=matching_tools[0].id,
                    name=matching_tools[0].name,
                    mcp_server_url=matching_tools[0].mcp_server_url,
                    parameters=json.loads(row[6]) if row[6] else {},
                )

        # Get expected_tool enriched data (from test case)
        expected_mcp_server_url = row[24]
        expected_tool_name = row[25]
        expected_parameters = json.loads(row[26]) if row[26] else None
        expected_tool = ToolEnrichedResponse(
            name=expected_tool_name,
            mcp_server_url=expected_mcp_server_url,
            parameters=expected_parameters,
        )

        return TestRunResponse(
            id=test_run_id,
            test_case_id=test_case_id,
            model_settings=model_settings,
            status=row[3],
            llm_response_raw=row[4],
            selected_tool=selected_tool,
            expected_tool=expected_tool,
            tools=tools,
            extracted_parameters=extracted_parameters,
            llm_confidence=row[7],
            parameter_correctness=row[8],
            confidence_score=row[9],
            classification=row[10],
            execution_time_ms=row[11],
            error_message=row[12],
            created_at=datetime.fromisoformat(row[13]),
            completed_at=datetime.fromisoformat(row[14]) if row[14] else None,
        )

    async def update_status(
        self,
        test_run_id: str,
        status: str,
        llm_response_raw: str | None = None,
        selected_tool_id: str | None = None,
        extracted_parameters: dict | None = None,
        llm_confidence: str | None = None,
        parameter_correctness: float | None = None,
        confidence_score: str | None = None,
        classification: str | None = None,
        execution_time_ms: int | None = None,
        error_message: str | None = None,
    ) -> TestRunResponse:
        """Update test run status and results.

        Args:
            test_run_id: Test run ID
            status: New status
            llm_response_raw: Raw LLM response JSON
            selected_tool_id: Tool selected by LLM
            extracted_parameters: Parameters extracted by LLM
            llm_confidence: LLM confidence level (high/low)
            parameter_correctness: Parameter correctness score (0-10)
            confidence_score: Confidence score description
            classification: Result classification (TP/FP/TN/FN)
            execution_time_ms: Execution time in milliseconds
            error_message: Error message if failed

        Returns:
            Updated test run

        Raises:
            ResourceNotFoundError: If test run not found
            DatabaseError: If database operation fails
        """
        # Verify test run exists
        await self.get(test_run_id)

        try:
            # Build update query
            updates = ["status = ?"]
            values = [status]

            if llm_response_raw is not None:
                updates.append("llm_response_raw = ?")
                values.append(llm_response_raw)

            if selected_tool_id is not None:
                updates.append("selected_tool_id = ?")
                values.append(selected_tool_id)

            if extracted_parameters is not None:
                updates.append("extracted_parameters = ?")
                values.append(json.dumps(extracted_parameters))

            if llm_confidence is not None:
                updates.append("llm_confidence = ?")
                values.append(llm_confidence)

            if parameter_correctness is not None:
                updates.append("parameter_correctness = ?")
                values.append(parameter_correctness)

            if confidence_score is not None:
                updates.append("confidence_score = ?")
                values.append(confidence_score)

            if classification is not None:
                updates.append("classification = ?")
                values.append(classification)

            if execution_time_ms is not None:
                updates.append("execution_time_ms = ?")
                values.append(execution_time_ms)

            if error_message is not None:
                updates.append("error_message = ?")
                values.append(error_message)

            if status in ["completed", "failed"]:
                updates.append("completed_at = CURRENT_TIMESTAMP")

            values.append(test_run_id)

            query = f"""
                UPDATE test_runs
                SET {", ".join(updates)}
                WHERE id = ?
            """  # nosec: "B608" Safe: updates list is internally controlled, values parameterized

            await self.db.execute(query, tuple(values))
            await self.db.commit()

            logger.info(f"Updated test run {test_run_id} status to {status}")

            return await self.get(test_run_id)

        except Exception as e:
            logger.error(f"Failed to update test run {test_run_id}: {e}")
            raise DatabaseError(f"Failed to update test run: {str(e)}", e) from e
