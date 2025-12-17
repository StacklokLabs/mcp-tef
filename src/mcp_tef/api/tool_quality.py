"""FastAPI router for tool quality evaluation endpoints.

WARNING: This endpoint performs high-intensity LLM operations.
A frontier model (e.g., GPT-4, Claude Opus/Sonnet) is strongly recommended.
Using smaller models may produce unexpected or inaccurate results.
"""

import asyncio

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import APIKeyHeader
from mcp_tef_models.schemas import (
    ToolQualityResponse,
    ToolQualityResult,
)

from mcp_tef.api.errors import BadRequestError
from mcp_tef.config.settings import Settings, get_settings
from mcp_tef.services.llm_service import LLMService
from mcp_tef.services.mcp_loader import MCPLoaderService
from mcp_tef.services.tool_quality_service import ToolQualityService

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_mcp_loader_service(request: Request) -> MCPLoaderService:
    """Dependency to get MCP loader service instance.

    Args:
        request: FastAPI request object

    Returns:
        MCPLoaderService instance
    """
    settings = request.app.state.settings
    return MCPLoaderService(timeout=settings.mcp_server_timeout)


@router.get(
    "/tools/quality",
    response_model=ToolQualityResponse,
    summary="Get quality evaluation and suggestions for MCP server tools by server url(s) "
    "(comma separated list). WARNING: High-intensity endpoint - frontier model recommended.",
    description="Evaluates MCP tool quality using LLM analysis. This is a computationally "
    "intensive operation that requires a frontier model (GPT-4, Claude Opus/Sonnet) "
    "for accurate results. Smaller models may produce unexpected or incorrect evaluations.",
)
async def get_mcp_server_tool_quality_by_url(
    server_urls: str = Query(description="MCP server url to get tools from"),
    transport: str = Query(
        default="streamable-http", description="Transport protocol: 'sse' or 'streamable-http'"
    ),
    model_provider: str = Query(description="Provider for quality evaluation model"),
    model_name: str = Query(description="Quality evaluation model"),
    mcp_loader_service: MCPLoaderService = Depends(get_mcp_loader_service),
    api_key: str | None = Depends(APIKeyHeader(name="X-Model-API-Key", auto_error=False)),
    settings: Settings = Depends(get_settings),
) -> ToolQualityResponse:
    """Evaluate tool quality for MCP servers.

    WARNING: This is a high-intensity endpoint that performs complex LLM analysis.
    A frontier model (GPT-4, Claude Opus/Sonnet) is strongly recommended for
    accurate results. Using smaller models may produce unexpected or incorrect
    evaluations.

    Args:
        server_urls: Comma-separated list of MCP server URLs
        transport: Transport protocol ('sse' or 'streamable-http')
        model_provider: LLM provider for quality evaluation
        model_name: LLM model name for quality evaluation
        mcp_loader_service: Service for loading MCP tools
        api_key: API key for the LLM provider
        settings: Application settings

    Returns:
        Quality evaluation results and suggestions for improvement
    """
    server_urls_list: list[str] = [url for url in server_urls.split(",") if url.strip()]
    if not server_urls_list:
        raise BadRequestError("empty server_urls")

    tasks = [
        _get_mcp_server_tool_quality_inner(
            server_url=url,
            transport=transport,
            model_provider=model_provider,
            model_name=model_name,
            mcp_loader_service=mcp_loader_service,
            api_key=api_key,
            settings=settings,
        )
        for url in server_urls_list
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    final_results: list[ToolQualityResult] = []
    errors: list[str] = []
    for url, result in zip(server_urls_list, results, strict=False):
        if isinstance(result, Exception):
            logger.error(f"Exception while evaluating tool quality for {url}", exc_info=result)
            errors.append(f"Error encountered while evaluating tools for {url}.")
        else:
            final_results.extend(result.results)
    return ToolQualityResponse(results=final_results, errors=errors if errors else None)


async def _get_mcp_server_tool_quality_inner(
    server_url: str,
    transport: str,
    model_provider: str,
    model_name: str,
    mcp_loader_service: MCPLoaderService,
    api_key: str | None,
    settings: Settings,
) -> ToolQualityResponse:
    llm_service = LLMService(
        model_provider,
        model_name,
        api_key,
        base_url=settings.get_base_url_for_provider(model_provider),
        settings=settings,
    )
    tool_quality_service = ToolQualityService(
        mcp_loader_service=mcp_loader_service,
        llm_service=llm_service,
    )
    quality_results = await tool_quality_service.evaluate_server(server_url, transport)
    return ToolQualityResponse(results=quality_results)
