"""Repository for tool call match database operations."""

import json
from typing import Any
from uuid import uuid4

import aiosqlite
import structlog

from mcp_tef.api.errors import DatabaseError

logger = structlog.get_logger(__name__)


class ToolCallMatchRepository:
    """Repository for managing tool call matches in SQLite."""

    def __init__(self, db: aiosqlite.Connection):
        """Initialize repository with database connection.

        Args:
            db: Active aiosqlite connection
        """
        self.db = db

    async def create(
        self,
        test_run_id: str,
        expected_tool_call_id: str | None,
        actual_tool_id: str | None,
        match_type: str,
        parameter_correctness: float | None,
        actual_parameters: dict[str, Any] | None = None,
        parameter_justification: str | None = None,
    ) -> str:
        """Create a new tool call match record.

        Args:
            test_run_id: Test run ID
            expected_tool_call_id: Expected tool call ID (None for FP)
            actual_tool_id: Actual tool ID (None for FN/TN)
            match_type: Match classification (TP/FP/FN/TN)
            parameter_correctness: Parameter correctness score (0-10)
            actual_parameters: Actual parameters from LLM (None for FN/TN)
            parameter_justification: Explanation of parameter score

        Returns:
            Created match ID

        Raises:
            DatabaseError: If database operation fails
        """
        match_id = str(uuid4())

        # Serialize actual_parameters to JSON if present
        actual_params_json = json.dumps(actual_parameters) if actual_parameters else None

        try:
            await self.db.execute(
                """
                INSERT INTO tool_call_matches
                (id, test_run_id, expected_tool_call_id, actual_tool_id,
                 match_type, parameter_correctness,
                 actual_parameters, parameter_justification)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    test_run_id,
                    expected_tool_call_id,
                    actual_tool_id,
                    match_type,
                    parameter_correctness,
                    actual_params_json,
                    parameter_justification,
                ),
            )
            await self.db.commit()
            logger.debug(
                "Created tool call match",
                match_id=match_id,
                test_run_id=test_run_id,
                match_type=match_type,
            )
            return match_id
        except Exception as e:
            logger.error(
                "Failed to create tool call match",
                test_run_id=test_run_id,
                match_type=match_type,
                error=str(e),
            )
            raise DatabaseError(f"Failed to create tool call match: {str(e)}", e) from e

    async def get_expected_call_id(self, test_case_id: str, sequence_order: int) -> str | None:
        """Get the ID of an expected tool call by its sequence order.

        Args:
            test_case_id: Test case ID
            sequence_order: Sequence order of the expected tool call

        Returns:
            Expected tool call ID or None if not found

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT id FROM expected_tool_calls
                WHERE test_case_id = ? AND sequence_order = ?
                """,
                (test_case_id, sequence_order),
            )
            row = await cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning(
                "Failed to get expected call ID",
                test_case_id=test_case_id,
                sequence_order=sequence_order,
                error=str(e),
            )
            raise DatabaseError(f"Failed to get expected call ID: {str(e)}", e) from e
