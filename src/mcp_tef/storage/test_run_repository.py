"""Repository for test run database operations."""

import json
from datetime import datetime
from sqlite3 import Row
from uuid import uuid4

import aiosqlite
import structlog
from mcp_tef_models.schemas import (
    ExpectedToolCall,
    ModelSettingsResponse,
    TestRunResponse,
    ToolCallMatch,
    ToolEnrichedResponse,
)

from mcp_tef.api.errors import DatabaseError, ResourceNotFoundError

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
        WHERE server_url = ?
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
    tr.llm_confidence,
    tr.avg_parameter_correctness,
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
GROUP BY {", ".join([str(i) for i in range(1, 23)])}
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
        [5]  tr.llm_confidence
        [6]  tr.avg_parameter_correctness
        [7]  tr.confidence_score
        [8]  tr.classification
        [9]  tr.execution_time_ms
        [10] tr.error_message
        [11] tr.created_at
        [12] tr.completed_at
        (model_settings)
        [13] ms.id
        [14] ms.provider
        [15] ms.model
        [16] ms.timeout
        [17] ms.temperature
        [18] ms.max_retries
        [19] ms.base_url
        [20] ms.system_prompt
        [21] ms.created_at
        (tools aggregate)
        [22] td_ids
        [23] td_names
        [24] td_mcp_server_urls
        [25] td_input_schemas

        Args:
            row: Database row from query

        Returns:
            Constructed TestRunResponse object
        """
        # Parse basic test run fields
        tools: list[ToolEnrichedResponse] = []
        if row[22] and row[22] != "None":
            tool_ids = json.loads(row[22])
            tool_names = json.loads(row[23])
            tool_mcp_server_urls = json.loads(row[24])
            tool_input_schemas = json.loads(row[25])
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

        # Build model_settings if present (LEFT JOIN, so may be NULL)
        model_settings = None
        if row[13]:  # ms.id is not NULL
            model_settings = ModelSettingsResponse(
                id=row[13],
                provider=row[14],
                model=row[15],
                timeout=row[16],
                temperature=row[17],
                max_retries=row[18],
                base_url=row[19],
                system_prompt=row[20],
                created_at=datetime.fromisoformat(row[21]),
            )

        # Fetch tool_call_matches for this test run
        tool_call_matches: list[ToolCallMatch] = []
        matches_cursor = await self.db.execute(
            """
            SELECT
                tcm.match_type,
                tcm.parameter_correctness,
                tcm.actual_parameters,
                tcm.parameter_justification,
                etc.mcp_server_url,
                etc.tool_name,
                etc.parameters,
                td.id,
                td.name,
                td.mcp_server_url,
                td.input_schema
            FROM tool_call_matches tcm
            LEFT JOIN expected_tool_calls etc ON tcm.expected_tool_call_id = etc.id
            LEFT JOIN tool_definitions td ON tcm.actual_tool_id = td.id
            WHERE tcm.test_run_id = ?
            """,
            (test_run_id,),
        )
        matches_rows = await matches_cursor.fetchall()
        for match_row in matches_rows:
            expected_tool_call = None
            if match_row[4]:  # expected mcp_server_url is not NULL
                expected_tool_call = ExpectedToolCall(
                    mcp_server_url=match_row[4],
                    tool_name=match_row[5],
                    parameters=json.loads(match_row[6]) if match_row[6] else None,
                )

            actual_tool_call = None
            if match_row[7]:  # actual tool id is not NULL
                actual_tool_call = ToolEnrichedResponse(
                    id=match_row[7],
                    name=match_row[8],
                    mcp_server_url=match_row[9],
                    parameters=json.loads(match_row[10]) if match_row[10] else None,
                )

            tool_call_matches.append(
                ToolCallMatch(
                    expected_tool_call=expected_tool_call,
                    actual_tool_call=actual_tool_call,
                    match_type=match_row[0],
                    parameter_correctness=match_row[1],
                    actual_parameters=json.loads(match_row[2]) if match_row[2] else None,
                    parameter_justification=match_row[3],
                )
            )

        return TestRunResponse(
            id=test_run_id,
            test_case_id=test_case_id,
            model_settings=model_settings,
            status=row[3],
            llm_response_raw=row[4],
            tools=tools,
            tool_call_matches=tool_call_matches,
            avg_parameter_correctness=row[6],
            llm_confidence=row[5],
            confidence_score=row[7],
            classification=row[8],
            execution_time_ms=row[9],
            error_message=row[10],
            created_at=datetime.fromisoformat(row[11]),
            completed_at=datetime.fromisoformat(row[12]) if row[12] else None,
        )

    async def update_status(
        self,
        test_run_id: str,
        status: str,
        llm_response_raw: str | None = None,
        llm_confidence: str | None = None,
        avg_parameter_correctness: float | None = None,
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
            llm_confidence: LLM confidence level (high/low)
            avg_parameter_correctness: Average parameter correctness across all tool call matches
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

            if llm_confidence is not None:
                updates.append("llm_confidence = ?")
                values.append(llm_confidence)

            if avg_parameter_correctness is not None:
                updates.append("avg_parameter_correctness = ?")
                values.append(avg_parameter_correctness)

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
