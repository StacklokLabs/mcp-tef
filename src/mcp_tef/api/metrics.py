"""FastAPI router for metrics endpoints."""

import structlog
from fastapi import APIRouter, Depends, Query, Request
from mcp_tef_models.schemas import MetricsSummaryResponse

from mcp_tef.services.metrics_service import MetricsService
from mcp_tef.storage.test_run_repository import TestRunRepository

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_test_run_repo(request: Request):
    """Dependency to get test run repository instance.

    Args:
        request: FastAPI request object

    Returns:
        TestRunRepository instance
    """
    return TestRunRepository(request.app.state.db)


def get_metrics_service(
    request: Request, test_run_repo=Depends(get_test_run_repo)
) -> MetricsService:
    """Dependency to get metrics service instance.

    Args:
        request: FastAPI request object

    Returns:
        MetricsService instance
    """
    return MetricsService(test_run_repo=test_run_repo)


@router.get(
    "/summary",
    response_model=MetricsSummaryResponse,
    summary="Get metrics summary",
    description="Get aggregated evaluation metrics across test runs filtered by server and/or tool",
    tags=["metrics"],
)
async def get_metrics_summary(
    test_run_id: str | None = Query(default=None),
    test_case_id: str | None = Query(default=None),
    mcp_server_url: str | None = Query(default=None),
    tool_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    metrics_service: MetricsService = Depends(get_metrics_service),
) -> MetricsSummaryResponse:
    """Get aggregated metrics summary with optional filters.

    Args:
        test_run_id: Optional test run ID to filter results.
        test_case_id: Optional test case ID to filter results.
        mcp_server_url: Optional MCP server URL to filter results.
        tool_name: Optional tool name to filter results (e.g., 'create_issue').
        limit: Maximum number of test runs to include in aggregation (default=100,
            min=1, max=1000).
        metrics_service: MetricsService instance injected by dependency.

    Returns:
        MetricsSummaryResponse: Aggregated metrics summary including precision, recall,
        F1 score, parameter accuracy, average execution time, counts for description
        categories, and test run IDs.

    Examples:
        GET /metrics/summary
        GET /metrics/summary?test_run_id=550e8400-e29b-41d4-a716-446655440000
        GET /metrics/summary?test_case_id=TC-123
        GET /metrics/summary?mcp_server_url=https://mcp.example.com&tool_name=create_issue
    """
    summary = await metrics_service.calculate_summary(
        test_run_id=test_run_id,
        test_case_id=test_case_id,
        mcp_server_url=mcp_server_url,
        tool_name=tool_name,
        limit=limit,
    )

    logger.info(
        "Metrics summary requested",
        total_tests=summary.total_tests,
        test_run_id=test_run_id,
        test_case_id=test_case_id,
        mcp_server_url=mcp_server_url,
        tool_name=tool_name,
    )

    return MetricsSummaryResponse(
        total_tests=summary.total_tests,
        true_positives=summary.true_positives,
        false_positives=summary.false_positives,
        true_negatives=summary.true_negatives,
        false_negatives=summary.false_negatives,
        precision=summary.precision,
        recall=summary.recall,
        f1_score=summary.f1_score,
        parameter_accuracy=summary.parameter_accuracy,
        average_execution_time_ms=summary.average_execution_time_ms,
        robust_description_count=summary.robust_description_count,
        needs_clarity_count=summary.needs_clarity_count,
        misleading_description_count=summary.misleading_description_count,
        test_run_ids=summary.test_run_ids,
    )
