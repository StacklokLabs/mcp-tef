"""Repository for test case database operations."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from uuid import uuid4

import aiosqlite
import structlog

from mcp_tef.api.errors import DatabaseError, ResourceNotFoundError, ValidationError
from mcp_tef.models.schemas import (
    MCPServerConfig,
    TestCaseCreate,
    TestCaseResponse,
)
from mcp_tef.services.mcp_loader import MCPLoaderService

logger = structlog.get_logger(__name__)


class TestCaseRepository:
    """Repository for managing test cases in SQLite."""

    def __init__(self, db: aiosqlite.Connection):
        """Initialize repository with database connection.

        Args:
            db: Active aiosqlite connection
        """
        self.db = db

    async def create(
        self,
        test_case: TestCaseCreate,
        mcp_loader: MCPLoaderService,
    ) -> TestCaseResponse:
        """Create a new test case with MCP server validation.

        User Story 2: Tools are NO LONGER stored during test case creation.
        Tools will be freshly ingested during test run execution.

        Args:
            test_case: Test case data
            mcp_server_repo: MCP server repository for lookups
            mcp_loader: MCP loader service for connecting to servers

        Returns:
            Created test case

        Raises:
            ValidationError: If validation fails (server not found, connection failure, etc.)
            DatabaseError: If database operation fails
        """
        test_case_id = str(uuid4())

        try:
            # Log start of operation
            logger.info(
                "Creating test case",
                name=test_case.name,
                servers=test_case.available_mcp_servers,
            )

            # Step 1: gather all tools for the MCP servers (fail fast for server connection issues)
            server_tools = {}  # server_url -> tools list
            load_server_tools_tasks = [
                mcp_loader.load_tools_from_server(server.url, server.transport)
                for server in test_case.available_mcp_servers
            ]
            server_tools_results = await asyncio.gather(*load_server_tools_tasks)
            for server_config, tools_list in zip(
                test_case.available_mcp_servers, server_tools_results, strict=True
            ):
                server_tools[server_config.url] = tools_list

            # Step 2: validate expected tools exist on expected server
            if test_case.expected_mcp_server_url:
                actual_tool_names = [
                    tool.name for tool in server_tools.get(test_case.expected_mcp_server_url, [])
                ]
                if test_case.expected_tool_name not in actual_tool_names:
                    raise ValidationError(
                        "Expected tool not found in expected MCP server tools",
                        {
                            "expected_tool_name": test_case.expected_tool_name,
                            "expected_mcp_server_url": test_case.expected_mcp_server_url,
                            "actual_tools": actual_tool_names,
                        },
                    )

            # Step 3-4: Insert test case and available MCP server associations
            try:
                # Step 3: Insert test case
                await self.db.execute(
                    """
                    INSERT INTO test_cases
                    (id, name, query, expected_mcp_server_url,
                     expected_tool_name, expected_parameters)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        test_case_id,
                        test_case.name,
                        test_case.query,
                        test_case.expected_mcp_server_url,
                        test_case.expected_tool_name,
                        (
                            json.dumps(test_case.expected_parameters)
                            if test_case.expected_parameters
                            else ""
                        ),
                    ),
                )

                # Step 4: Insert MCP server associations
                for server_config in test_case.available_mcp_servers:
                    await self.db.execute(
                        """
                        INSERT INTO test_case_mcp_servers (test_case_id, server_url, transport)
                        VALUES (?, ?, ?)
                        """,
                        (
                            test_case_id,
                            server_config.url,
                            server_config.transport,
                        ),
                    )

                await self.db.commit()
            except Exception as e:
                await self.db.rollback()
                logger.error(
                    "Transaction failed, rolling back",
                    test_case_id=test_case_id,
                    error=str(e),
                )
                raise DatabaseError(f"Failed to insert test case: {str(e)}", e) from e

            # Log completion with metrics
            logger.info(
                "Created test case",
                test_case_id=test_case_id,
                name=test_case.name,
                servers_count=len(test_case.available_mcp_servers),
            )

            return await self.get(test_case_id)

        except ValidationError:
            raise
        except Exception as e:
            logger.error("Failed to create test case", error=str(e))
            raise DatabaseError(f"Failed to create test case: {str(e)}", e) from e

    async def get(
        self,
        test_case_id: str,
    ) -> TestCaseResponse:
        """Get a test case by ID.

        Args:
            test_case_id: Test case ID
            mcp_server_repo: Optional MCP server repository for resolving server names

        Returns:
            Test case

        Raises:
            ResourceNotFoundError: If test case not found
            DatabaseError: If database operation fails
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT id, name, query, expected_mcp_server_url,
                       expected_tool_name, expected_parameters, created_at, updated_at
                FROM test_cases
                WHERE id = ?
                """,
                (test_case_id,),
            )
            row = await cursor.fetchone()

            if row is None:
                raise ResourceNotFoundError("TestCase", test_case_id)

            # Get MCP servers from junction table and reconstruct list
            servers_cursor = await self.db.execute(
                """
                SELECT server_url, transport
                FROM test_case_mcp_servers
                WHERE test_case_id = ?
                """,
                (test_case_id,),
            )
            server_rows = await servers_cursor.fetchall()
            available_mcp_servers = [
                MCPServerConfig(url=server_url, transport=transport)
                for server_url, transport in server_rows
            ]

            return TestCaseResponse(
                id=row[0],
                name=row[1],
                query=row[2],
                expected_mcp_server_url=row[3],
                expected_tool_name=row[4],
                expected_parameters=json.loads(row[5]) if row[5] else None,
                available_mcp_servers=available_mcp_servers,
                created_at=datetime.fromisoformat(row[6]),
                updated_at=datetime.fromisoformat(row[7]),
            )

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error("Failed to get test case", test_case_id=test_case_id, error=str(e))
            raise DatabaseError(f"Failed to get test case: {str(e)}", e) from e

    async def list(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[TestCaseResponse], int]:
        """List test cases with pagination.

        Args:
            offset: Number of records to skip
            limit: Maximum number of records to return
            mcp_server_repo: Optional MCP server repository for resolving server names

        Returns:
            Tuple of (list of test cases, total count)

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Get total count
            cursor = await self.db.execute("SELECT COUNT(*) FROM test_cases")
            total = (await cursor.fetchone())[0]

            # Get paginated results
            cursor = await self.db.execute(
                """
                SELECT id, name, query, expected_mcp_server_url,
                       expected_tool_name, expected_parameters, created_at, updated_at
                FROM test_cases
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = await cursor.fetchall()

            if not rows:
                return [], total

            # Batch fetch all servers for all test cases to avoid N+1 queries
            test_case_ids = [row[0] for row in rows]
            placeholders = ",".join("?" * len(test_case_ids))
            servers_cursor = await self.db.execute(
                f"""
                SELECT test_case_id, server_url, transport
                FROM test_case_mcp_servers
                WHERE test_case_id IN ({placeholders})
                """,  # nosec: "B608" Safe: placeholders is internally generated, values are parameterized
                test_case_ids,
            )
            server_associations = await servers_cursor.fetchall()

            # Build mapping of test_case_id -> list[MCPServerConfig]
            test_case_servers = {}
            for test_case_id, server_url, transport in server_associations:
                if test_case_id not in test_case_servers:
                    test_case_servers[test_case_id] = []
                test_case_servers[test_case_id].append(
                    MCPServerConfig(url=server_url, transport=transport)
                )

            # Build test case responses
            test_cases = []
            for row in rows:
                test_case_id = row[0]
                available_mcp_servers = test_case_servers.get(test_case_id, [])

                test_cases.append(
                    TestCaseResponse(
                        id=test_case_id,
                        name=row[1],
                        query=row[2],
                        expected_mcp_server_url=row[3],
                        expected_tool_name=row[4],
                        expected_parameters=json.loads(row[5]) if row[5] else None,
                        available_mcp_servers=available_mcp_servers,
                        created_at=datetime.fromisoformat(row[6]),
                        updated_at=datetime.fromisoformat(row[7]),
                    )
                )

            return test_cases, total

        except Exception as e:
            logger.error("Failed to list test cases", error=str(e))
            raise DatabaseError(f"Failed to list test cases: {str(e)}", e) from e

    async def get_test_case_servers(
        self,
        test_case_id: str,
    ) -> list[MCPServerConfig]:
        """Get MCP server configurations for test case.

        Args:
            test_case_id: Test case ID

        Returns:
            List of MCPServerConfig objects

        Raises:
            ResourceNotFoundError: If test case not found
            DatabaseError: If database operation fails
        """
        try:
            # Verify test case exists
            await self.get(test_case_id)

            # Get MCP server configurations from junction table
            cursor = await self.db.execute(
                """
                SELECT server_url, transport
                FROM test_case_mcp_servers
                WHERE test_case_id = ?
                """,
                (test_case_id,),
            )
            rows = await cursor.fetchall()
            return [MCPServerConfig(url=row[0], transport=row[1]) for row in rows]

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to get test case servers",
                test_case_id=test_case_id,
                error=str(e),
            )
            raise DatabaseError(f"Failed to get test case servers: {str(e)}", e) from e

    async def delete(self, test_case_id: str) -> None:
        """Delete a test case.

        Args:
            test_case_id: Test case ID

        Raises:
            ResourceNotFoundError: If test case not found
            DatabaseError: If database operation fails
        """
        # Verify test case exists
        await self.get(test_case_id)

        try:
            await self.db.execute(
                "DELETE FROM test_cases WHERE id = ?",
                (test_case_id,),
            )
            await self.db.commit()

            logger.info(f"Deleted test case: {test_case_id}")

        except Exception as e:
            logger.error(f"Failed to delete test case {test_case_id}: {e}")
            raise DatabaseError(f"Failed to delete test case: {str(e)}", e) from e
