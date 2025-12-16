"""Repository for tool definition database operations."""

import json
from datetime import datetime
from sqlite3 import IntegrityError
from uuid import uuid4

import aiosqlite
import structlog
from mcp_tef_models.schemas import (
    ToolDefinitionCreate,
    ToolDefinitionResponse,
)

from mcp_tef.api.errors import DatabaseError, ResourceNotFoundError, ValidationError

logger = structlog.get_logger(__name__)


class ToolRepository:
    """Repository for managing tool definitions in SQLite."""

    def __init__(self, db: aiosqlite.Connection):
        """Initialize repository with database connection.

        Args:
            db: Active aiosqlite connection
        """
        self.db = db

    async def create(
        self, tool: ToolDefinitionCreate, commit: bool = True
    ) -> ToolDefinitionResponse:
        """Create a new tool definition.

        Args:
            tool: Tool definition data
            commit: Whether to commit the transaction (default: True)

        Returns:
            Created tool definition

        Raises:
            ValidationError: If tool name already exists
            DatabaseError: If database operation fails
        """
        tool_id = str(uuid4())

        try:
            await self.db.execute(
                """
                INSERT INTO tool_definitions
                (id, name, description, input_schema, output_schema, mcp_server_url, test_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tool_id,
                    tool.name,
                    tool.description,
                    json.dumps(tool.input_schema),
                    json.dumps(tool.output_schema) if tool.output_schema else None,
                    tool.mcp_server_url,
                    tool.test_run_id,
                ),
            )
            if commit:
                await self.db.commit()

            logger.info("Created tool definition", tool_id=tool_id, tool_name=tool.name)

            return await self.get(tool_id)

        except IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                raise ValidationError(
                    f"Tool with name '{tool.name}' already exists",
                    {"name": tool.name},
                ) from e
            raise DatabaseError(f"Failed to create tool: {str(e)}", e) from e
        except Exception as e:
            logger.error("Failed to create tool definition", error=str(e))
            raise DatabaseError(f"Failed to create tool: {str(e)}", e) from e

    async def batch_create(
        self, tools: list[ToolDefinitionCreate], commit: bool = True
    ) -> tuple[list[ToolDefinitionResponse], list[str]]:
        """Create multiple tool definitions in a single batch operation.

        This method attempts a batch insert for optimal performance. If the batch insert
        fails due to duplicate names, it automatically falls back to individual inserts,
        skipping tools with duplicate names and continuing with the rest.

        Args:
            tools: List of tool definition data
            commit: Whether to commit the transaction (default: True)

        Returns:
            Tuple of (successfully created tools, list of skipped tool names).
            Tools are skipped if their names already exist in the database.

        Raises:
            DatabaseError: If database operation fails
        """
        if not tools:
            return [], []

        created_tools = []
        skipped_tools = []

        # Prepare batch insert data
        values = []
        tool_ids = []
        for tool in tools:
            tool_id = str(uuid4())
            tool_ids.append((tool_id, tool.name))
            values.append(
                (
                    tool_id,
                    tool.name,
                    tool.description,
                    json.dumps(tool.input_schema),
                    json.dumps(tool.output_schema) if tool.output_schema else None,
                    tool.mcp_server_url,
                    tool.test_run_id,
                )
            )

        try:
            # Execute batch insert
            await self.db.executemany(
                """
                INSERT INTO tool_definitions
                (id, name, description, input_schema, output_schema, mcp_server_url, test_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

            if commit:
                await self.db.commit()

            # Fetch all created tools
            for tool_id, tool_name in tool_ids:
                try:
                    tool = await self.get(tool_id)
                    created_tools.append(tool)
                except Exception:
                    # If tool wasn't created (e.g., duplicate), add to skipped
                    skipped_tools.append(tool_name)

            logger.info(
                "Batch created tool definitions",
                total_requested=len(tools),
                total_created=len(created_tools),
                total_skipped=len(skipped_tools),
            )

            return created_tools, skipped_tools

        except Exception as e:
            logger.error("Failed to batch create tool definitions", error=str(e))
            raise DatabaseError(f"Failed to batch create tools: {str(e)}", e) from e

    async def get(self, tool_id: str) -> ToolDefinitionResponse:
        """Get a tool definition by ID.

        Args:
            tool_id: Tool definition ID

        Returns:
            Tool definition

        Raises:
            ResourceNotFoundError: If tool not found
            DatabaseError: If database operation fails
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT id, name, description, input_schema, output_schema,
                       mcp_server_url, test_run_id, created_at
                FROM tool_definitions
                WHERE id = ?
                """,
                (tool_id,),
            )
            row = await cursor.fetchone()

            if row is None:
                raise ResourceNotFoundError("ToolDefinition", tool_id)

            return ToolDefinitionResponse(
                id=row[0],
                name=row[1],
                description=row[2],
                input_schema=json.loads(row[3]),
                output_schema=json.loads(row[4]) if row[4] else None,
                mcp_server_url=row[5],
                test_run_id=row[6],
                created_at=datetime.fromisoformat(row[7]),
            )

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error("Failed to get tool definition", tool_id=tool_id, error=str(e))
            raise DatabaseError(f"Failed to get tool: {str(e)}", e) from e

    async def get_by_name(self, tool_name: str) -> ToolDefinitionResponse:
        """Get a tool definition by name.

        Args:
            tool_name: Tool name

        Returns:
            Tool definition

        Raises:
            ResourceNotFoundError: If tool not found
            DatabaseError: If database operation fails
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT id, name, description, input_schema, output_schema,
                       mcp_server_url, test_run_id, created_at
                FROM tool_definitions
                WHERE name = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (tool_name,),
            )
            row = await cursor.fetchone()

            if row is None:
                raise ResourceNotFoundError("ToolDefinition", tool_name)

            return ToolDefinitionResponse(
                id=row[0],
                name=row[1],
                description=row[2],
                input_schema=json.loads(row[3]),
                output_schema=json.loads(row[4]) if row[4] else None,
                mcp_server_url=row[5],
                test_run_id=row[6],
                created_at=datetime.fromisoformat(row[7]),
            )

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to get tool definition by name",
                tool_name=tool_name,
                error=str(e),
            )
            raise DatabaseError(f"Failed to get tool: {str(e)}", e) from e

    async def get_by_name_and_test_run(
        self, tool_name: str, test_run_id: str
    ) -> ToolDefinitionResponse:
        """Get a tool definition by name and test run ID.

        Args:
            tool_name: Tool name
            test_run_id: Test run ID

        Returns:
            Tool definition

        Raises:
            ResourceNotFoundError: If tool not found
            DatabaseError: If database operation fails
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT id, name, description, input_schema, output_schema,
                       mcp_server_url, test_run_id, created_at
                FROM tool_definitions
                WHERE name = ? AND test_run_id = ?
                """,
                (tool_name, test_run_id),
            )
            row = await cursor.fetchone()

            if row is None:
                raise ResourceNotFoundError(
                    "ToolDefinition",
                    f"name={tool_name}, test_run_id={test_run_id}",
                )

            return ToolDefinitionResponse(
                id=row[0],
                name=row[1],
                description=row[2],
                input_schema=json.loads(row[3]),
                output_schema=json.loads(row[4]) if row[4] else None,
                mcp_server_url=row[5],
                test_run_id=row[6],
                created_at=datetime.fromisoformat(row[7]),
            )

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to get tool by name and test run",
                tool_name=tool_name,
                test_run_id=test_run_id,
                error=str(e),
            )
            raise DatabaseError(f"Failed to get tool: {str(e)}", e) from e

    async def get_by_server_url_and_test_run(
        self, mcp_server_url: str, tool_name: str, test_run_id: str
    ) -> ToolDefinitionResponse:
        """Get a tool definition by server ID, tool name, and test run ID.

        Args:
            mcp_server_url: MCP server url
            tool_name: Tool name
            test_run_id: Test run ID

        Returns:
            Tool definition

        Raises:
            ResourceNotFoundError: If tool not found
            DatabaseError: If database operation fails
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT id, name, description, input_schema, output_schema,
                       mcp_server_url, test_run_id, created_at
                FROM tool_definitions
                WHERE mcp_server_url = ? AND name = ? AND test_run_id = ?
                """,
                (mcp_server_url, tool_name, test_run_id),
            )
            row = await cursor.fetchone()

            if row is None:
                raise ResourceNotFoundError(
                    "ToolDefinition",
                    f"server={mcp_server_url}, name={tool_name}, test_run_id={test_run_id}",
                )

            return ToolDefinitionResponse(
                id=row[0],
                name=row[1],
                description=row[2],
                input_schema=json.loads(row[3]),
                output_schema=json.loads(row[4]) if row[4] else None,
                mcp_server_url=row[5],
                test_run_id=row[6],
                created_at=datetime.fromisoformat(row[7]),
            )

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to get tool by server, name and test run",
                mcp_server_url=mcp_server_url,
                tool_name=tool_name,
                test_run_id=test_run_id,
                error=str(e),
            )
            raise DatabaseError(f"Failed to get tool: {str(e)}", e) from e

    async def list_all(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[ToolDefinitionResponse], int]:
        """List all tool definitions with pagination.

        Args:
            offset: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (list of tools, total count)

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Get total count
            cursor = await self.db.execute("SELECT COUNT(*) FROM tool_definitions")
            total = (await cursor.fetchone())[0]

            # Get paginated results
            cursor = await self.db.execute(
                """
                SELECT id, name, description, input_schema, output_schema,
                       mcp_server_url, test_run_id, created_at
                FROM tool_definitions
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = await cursor.fetchall()

            tools = [
                ToolDefinitionResponse(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    input_schema=json.loads(row[3]),
                    output_schema=json.loads(row[4]) if row[4] else None,
                    mcp_server_url=row[5],
                    test_run_id=row[6],
                    created_at=datetime.fromisoformat(row[7]),
                )
                for row in rows
            ]

            return tools, total

        except Exception as e:
            logger.error("Failed to list tool definitions", error=str(e))
            raise DatabaseError(f"Failed to list tools: {str(e)}", e) from e

    async def list_by_test_run(
        self,
        test_run_id: str,
        offset: int = 0,
        limit: int = 1000,
    ) -> tuple[list[ToolDefinitionResponse], int]:
        """List tool definitions for a specific test run pagination.

        Args:
            test_run_id: Test run to filter by
            offset: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (list of tools, total count)

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Get total count for this server
            cursor = await self.db.execute(
                "SELECT COUNT(*) FROM tool_definitions WHERE test_run_id = ?",
                (test_run_id,),
            )
            total = (await cursor.fetchone())[0]

            # Get paginated results for this server
            cursor = await self.db.execute(
                """
                SELECT id, name, description, input_schema, output_schema,
                       mcp_server_url, test_run_id, created_at
                FROM tool_definitions
                WHERE test_run_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (test_run_id, limit, offset),
            )
            rows = await cursor.fetchall()

            tools = [
                ToolDefinitionResponse(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    input_schema=json.loads(row[3]),
                    output_schema=json.loads(row[4]) if row[4] else None,
                    mcp_server_url=row[5],
                    test_run_id=row[6],
                    created_at=datetime.fromisoformat(row[7]),
                )
                for row in rows
            ]

            logger.debug(f"Found {len(tools)} tools for test run {test_run_id}")
            return tools, total

        except Exception as e:
            logger.error(
                "Failed to list tools for test run",
                test_run_id=test_run_id,
                error=str(e),
            )
            raise DatabaseError(f"Failed to list tools by server: {str(e)}", e) from e
