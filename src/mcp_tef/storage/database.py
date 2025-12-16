"""Database connection management for SQLite with aiosqlite."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


class DatabaseManager:
    """Manages SQLite database connection lifecycle."""

    def __init__(self, database_url: str):
        """Initialize database manager.

        Args:
            database_url: SQLite database URL (e.g., "sqlite:///./mcp_eval.db")
        """
        # Extract path from sqlite:/// URL format
        self.database_path = database_url.replace("sqlite:///", "")
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> aiosqlite.Connection:
        """Establish database connection and initialize schema.

        Returns:
            Active database connection with row factory configured
        """
        self._connection = await aiosqlite.connect(self.database_path)
        self._connection.row_factory = aiosqlite.Row

        # Enable foreign key constraints
        await self._connection.execute("PRAGMA foreign_keys = ON")

        # Enable WAL mode for better concurrency
        await self._connection.execute("PRAGMA journal_mode = WAL")

        # Initialize schema
        await self._initialize_schema()

        return self._connection

    async def _initialize_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        if self._connection is None:
            raise RuntimeError("Database connection not established. Call connect() first.")

        schema_path = Path(__file__).parent / "schema.sql"

        with open(schema_path) as f:
            schema_sql = f.read()

        await self._connection.executescript(schema_sql)
        await self._connection.commit()

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get active connection.

        Raises:
            RuntimeError: If connection is not established
        """
        if self._connection is None:
            raise RuntimeError("Database connection not established. Call connect() first.")
        return self._connection


@asynccontextmanager
async def get_database_connection(database_url: str) -> AsyncGenerator[aiosqlite.Connection]:
    """Context manager for database connections.

    Args:
        database_url: SQLite database URL

    Yields:
        Active database connection

    Example:
        async with get_database_connection("sqlite:///./test.db") as db:
            cursor = await db.execute("SELECT * FROM table")
            rows = await cursor.fetchall()
    """
    manager = DatabaseManager(database_url)
    connection = await manager.connect()
    try:
        yield connection
    finally:
        await manager.close()
