"""FastAPI router for test case endpoints."""

import asyncio

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from fastapi.security import APIKeyHeader

from mcp_tef.config.settings import Settings, get_settings
from mcp_tef.models.schemas import (
    MCPServerConfig,
    PaginatedTestCaseResponse,
    TestCaseCreate,
    TestCaseResponse,
    TestRunExecuteRequest,
    TestRunResponse,
    ToolDefinition,
)
from mcp_tef.services.evaluation_service import EvaluationService
from mcp_tef.services.mcp_loader import MCPLoaderService
from mcp_tef.storage.model_settings_repository import ModelSettingsRepository
from mcp_tef.storage.test_case_repository import TestCaseRepository
from mcp_tef.storage.test_run_repository import TestRunRepository
from mcp_tef.storage.tool_repository import ToolRepository

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_test_case_repository(request: Request) -> TestCaseRepository:
    """Dependency to get test case repository instance.

    Args:
        request: FastAPI request object

    Returns:
        TestCaseRepository instance with database connection
    """
    return TestCaseRepository(request.app.state.db)


def get_tool_repository(request: Request) -> ToolRepository:
    """Dependency to get tool repository instance.

    Args:
        request: FastAPI request object

    Returns:
        ToolRepository instance with database connection
    """
    return ToolRepository(request.app.state.db)


def get_mcp_loader_service(request: Request) -> MCPLoaderService:
    """Dependency to get MCP loader service instance.

    Args:
        request: FastAPI request object

    Returns:
        MCPLoaderService instance
    """
    settings = request.app.state.settings
    return MCPLoaderService(timeout=settings.mcp_server_timeout)


def get_evaluation_service(
    request: Request, settings: Settings = Depends(get_settings)
) -> EvaluationService:
    """Dependency to get evaluation service instance.

    Args:
        request: FastAPI request object
        settings: Application settings

    Returns:
        EvaluationService instance
    """
    db = request.app.state.db
    return EvaluationService(
        test_case_repo=TestCaseRepository(db),
        test_run_repo=TestRunRepository(db),
        model_settings_repo=ModelSettingsRepository(db),
        tool_repo=ToolRepository(db),
        mcp_loader=MCPLoaderService(timeout=settings.mcp_server_timeout),
        settings=settings,
    )


def get_test_run_repository(request: Request) -> TestRunRepository:
    """Dependency to get test run repository instance.

    Args:
        request: FastAPI request object

    Returns:
        TestRunRepository instance
    """
    return TestRunRepository(request.app.state.db)


@router.post(
    "",
    response_model=TestCaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create test case",
    description="Create a new test case for tool selection evaluation with MCP server validation",
)
async def create_test_case(
    test_case: TestCaseCreate,
    repo: TestCaseRepository = Depends(get_test_case_repository),
    mcp_loader: MCPLoaderService = Depends(get_mcp_loader_service),
) -> TestCaseResponse:
    """Create a new test case with MCP server validation.

    This endpoint validates that all referenced MCP servers exist and are reachable,
    and that the expected tool exists in the expected MCP server.

    User Story 2: Tools are NO LONGER stored during test case creation.
    Tools will be freshly ingested during test run execution.

    Args:
        test_case: Test case data
        repo: Test case repository instance
        mcp_server_repo: MCP server repository instance
        mcp_loader: MCP loader service instance

    Returns:
        Created test case

    Raises:
        ValidationError: If MCP servers not found or connection fails
    """
    return await repo.create(test_case, mcp_loader)


@router.get(
    "",
    response_model=PaginatedTestCaseResponse,
    summary="List test cases",
    description="Get a paginated list of all test cases",
)
async def list_test_cases(
    offset: int = 0,
    limit: int = 100,
    mcp_loader: MCPLoaderService = Depends(get_mcp_loader_service),
    repo: TestCaseRepository = Depends(get_test_case_repository),
) -> PaginatedTestCaseResponse:
    """List all test cases with pagination.

    Args:
        offset: Number of records to skip (default: 0)
        limit: Maximum number of records to return (default: 100)
        repo: Test case repository instance
        mcp_server_repo: MCP server repository instance

    Returns:
        Paginated list of test cases, not including available tools (use GET /test_case_id)
    """
    test_cases, total = await repo.list(offset=offset, limit=limit)

    return PaginatedTestCaseResponse(
        items=test_cases,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{test_case_id}",
    response_model=TestCaseResponse,
    summary="Get test case",
    description="Get a specific test case by ID",
)
async def get_test_case(
    test_case_id: str,
    mcp_loader: MCPLoaderService = Depends(get_mcp_loader_service),
    repo: TestCaseRepository = Depends(get_test_case_repository),
) -> TestCaseResponse:
    """Get a specific test case.

    Args:
        test_case_id: Test case ID
        repo: Test case repository instance
        mcp_server_repo: MCP server repository instance

    Returns:
        Test case

    Raises:
        ResourceNotFoundError: If test case not found
    """
    response = await repo.get(test_case_id)
    response.available_tools = await _gather_tools_for_servers(
        response.available_mcp_servers, mcp_loader
    )
    return response


async def _gather_tools_for_servers(
    mcp_servers: list[MCPServerConfig], mcp_loader: MCPLoaderService
) -> dict[str, list[ToolDefinition]]:
    """
    Gather tools from MCP servers.

    Returns:
        dict of server_url -> tools
    """
    gather_tools_tasks = [
        mcp_loader.load_tools_from_server(server.url, server.transport) for server in mcp_servers
    ]
    gather_tools_results = await asyncio.gather(*gather_tools_tasks)
    return dict(zip([server.url for server in mcp_servers], gather_tools_results, strict=False))


@router.delete(
    "/{test_case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete test case",
    description="Delete a test case",
)
async def delete_test_case(
    test_case_id: str,
    repo: TestCaseRepository = Depends(get_test_case_repository),
) -> None:
    """Delete a test case.

    Args:
        test_case_id: Test case ID
        repo: Test case repository instance

    Raises:
        ResourceNotFoundError: If test case not found
    """
    await repo.delete(test_case_id)


@router.post(
    "/{test_case_id}/run",
    response_model=TestRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run test case",
    description="Execute a test case with runtime API key and model configuration",
)
async def run_test_case(
    test_case_id: str,
    execute_request: TestRunExecuteRequest,
    background_tasks: BackgroundTasks,
    api_key: str | None = Depends(APIKeyHeader(name="X-Model-API-Key", auto_error=False)),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
) -> TestRunResponse:
    """Run a test case with optional runtime API key and model settings.

    User Story 2: Tool ingestion happens during test run execution to ensure fresh tools.

    Args:
        test_case_id: Test case ID to execute
        execute_request: Test execution request with model_settings
        background_tasks: FastAPI background tasks
        api_key: Optional runtime API key from X-Model-API-Key header
        evaluation_service: Evaluation service instance

    Returns:
        Test run with model_settings persisted (initially pending, will be updated in background)
    """
    test_run = await evaluation_service.create_test(test_case_id, execute_request.model_settings)
    background_tasks.add_task(evaluation_service.execute_pending_test, test_run, api_key)
    return test_run
