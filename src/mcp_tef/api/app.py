"""FastAPI application setup with lifespan events and error handlers."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mcp_tef.api import (
    mcp_servers,
    metrics,
    similarity,
    test_cases,
    test_runs,
)
from mcp_tef.api.errors import (
    MCPEvalException,
    generic_exception_handler,
    mcp_eval_exception_handler,
)
from mcp_tef.config.logging_config import setup_logging
from mcp_tef.config.settings import Settings, get_settings
from mcp_tef.storage.database import DatabaseManager

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifecycle events.

    Args:
        app: FastAPI application instance

    Yields:
        None during application runtime
    """
    # Startup
    settings: Settings = app.state.settings
    setup_logging(
        log_level=settings.log_level,
        colored_logs=settings.colored_logs,
        rich_tracebacks=settings.rich_tracebacks,
    )
    logger.info("Starting MCP Tool Evaluation System")
    logger.info(f"Database: {settings.database_url}")
    logger.info(f"Default LLM: {settings.default_model.provider}/{settings.default_model.name}")

    # Initialize database
    db_manager = DatabaseManager(settings.database_url)
    app.state.db = await db_manager.connect()
    logger.info("Database connection established")

    yield

    # Shutdown
    logger.info("Shutting down MCP Tool Evaluation System")
    await db_manager.close()
    logger.info("Database connection closed")


settings = get_settings()

app = FastAPI(
    title="MCP Tool Evaluation System",
    description="Validate tool selection effectiveness for Model Context Protocol tools",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Store settings in app state
app.state.settings = settings

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]  # ty limitation with FastAPI middleware factory types
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exception handlers
app.add_exception_handler(MCPEvalException, mcp_eval_exception_handler)  # type: ignore[arg-type]  # ty limitation with async handler types
app.add_exception_handler(Exception, generic_exception_handler)  # type: ignore[arg-type]  # ty limitation with async handler types

# Register routers
app.include_router(mcp_servers.router, prefix="/mcp-servers", tags=["mcp-servers"])
app.include_router(test_cases.router, prefix="/test-cases", tags=["test-cases"])
app.include_router(test_runs.router, prefix="/test-runs", tags=["test-runs"])
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
app.include_router(similarity.router, prefix="/similarity", tags=["similarity"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "MCP Tool Evaluation System",
        "version": "0.1.0",
        "status": "healthy",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
