"""FastAPI router for test run endpoints."""

import structlog
from fastapi import APIRouter, Depends, Query, Request
from mcp_tef_models.schemas import PaginatedTestRunResponse, TestRunResponse

from mcp_tef.storage.test_run_repository import TestRunRepository

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_test_run_repository(request: Request) -> TestRunRepository:
    """Dependency to get test run repository instance.

    Args:
        request: FastAPI request object

    Returns:
        TestRunRepository instance
    """
    return TestRunRepository(request.app.state.db)


@router.get(
    "/{test_run_id}",
    response_model=TestRunResponse,
    summary="Get test run",
    description="Get test run status and results",
    tags=["test-runs"],
)
async def get_test_run(
    test_run_id: str,
    repo: TestRunRepository = Depends(get_test_run_repository),
) -> TestRunResponse:
    """Get a test run.

    Args:
        test_run_id: Test run ID
        repo: Test run repository instance

    Returns:
        Test run with status and results

    Raises:
        ResourceNotFoundError: If test run not found
    """
    return await repo.get(test_run_id)


@router.get(
    "",
    response_model=PaginatedTestRunResponse,
    summary="Get test runs",
    tags=["test-runs"],
)
async def get_test_runs(
    test_run_id: str | None = Query(default=None),
    test_case_id: str | None = Query(default=None),
    mcp_server_url: str | None = Query(default=None),
    tool_name: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    test_run_repo: TestRunRepository = Depends(get_test_run_repository),
) -> PaginatedTestRunResponse:
    """Get test runs for the given query.

    Args:
        test_run_id: Retrieves an individual test run by id
        test_case_id: Retrieves all test runs for a given test case id
        mcp_server_url: Retrieves all test_runs for a given MCP server
        tool_name: Retrieves test runs filtered by selected tool name (chosen by LLM)
        offset: Number of results to skip (default: 0)
        limit: Maximum number of results to return (default: 100, max: 1000)

    Returns:
        Test runs.
    """
    test_runs = await test_run_repo.query(
        test_run_id=test_run_id,
        test_case_id=test_case_id,
        mcp_server_url=mcp_server_url,
        tool_name=tool_name,
        offset=offset,
        limit=limit,
    )
    return PaginatedTestRunResponse(
        items=test_runs, total=len(test_runs), offset=offset, limit=limit
    )
