"""Repository for model settings database operations."""

from datetime import datetime
from uuid import uuid4

import aiosqlite
import structlog
from mcp_tef_models.schemas import (
    ModelSettingsCreate,
    ModelSettingsResponse,
)

from mcp_tef.api.errors import DatabaseError, ResourceNotFoundError

logger = structlog.get_logger(__name__)


class ModelSettingsRepository:
    """Repository for managing model settings in SQLite."""

    def __init__(self, db: aiosqlite.Connection):
        """Initialize repository with database connection.

        Args:
            db: Active aiosqlite connection
        """
        self.db = db

    async def create(self, model_settings: ModelSettingsCreate) -> ModelSettingsResponse:
        """Create a new model settings record.

        Args:
            model_settings: Model configuration data (without API key)

        Returns:
            Created model settings

        Raises:
            DatabaseError: If database operation fails
        """
        settings_id = str(uuid4())

        try:
            await self.db.execute(
                """
                INSERT INTO model_settings
                (id, provider, model, timeout, temperature, max_retries, base_url, system_prompt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    settings_id,
                    model_settings.provider,
                    model_settings.model,
                    model_settings.timeout,
                    model_settings.temperature,
                    model_settings.max_retries,
                    model_settings.base_url,
                    model_settings.system_prompt,
                ),
            )
            await self.db.commit()

            logger.info(
                f"Created model settings: {settings_id} "
                f"({model_settings.provider}/{model_settings.model})"
            )

            # Retrieve the created settings
            return await self.get(settings_id)

        except Exception as e:
            logger.error(f"Failed to create model settings: {e}")
            raise DatabaseError(f"Failed to create model settings: {str(e)}", e) from e

    async def get(self, settings_id: str) -> ModelSettingsResponse:
        """Get model settings by ID.

        Args:
            settings_id: Model settings ID

        Returns:
            Model settings

        Raises:
            ResourceNotFoundError: If settings not found
            DatabaseError: If database operation fails
        """
        try:
            cursor = await self.db.execute(
                """
                SELECT
                    id, provider, model, timeout, temperature, max_retries,
                    base_url, system_prompt, created_at
                FROM model_settings
                WHERE id = ?
                """,
                (settings_id,),
            )
            row = await cursor.fetchone()

            if row is None:
                raise ResourceNotFoundError("ModelSettings", settings_id)

            return ModelSettingsResponse(
                id=row[0],
                provider=row[1],
                model=row[2],
                timeout=row[3],
                temperature=row[4],
                max_retries=row[5],
                base_url=row[6],
                system_prompt=row[7],
                created_at=datetime.fromisoformat(row[8]),
            )

        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get model settings {settings_id}: {e}")
            raise DatabaseError(f"Failed to get model settings: {str(e)}", e) from e
