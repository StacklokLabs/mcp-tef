"""API endpoints for tool similarity analysis."""

from datetime import UTC, datetime
from typing import Any, Literal, cast

import structlog
from fastapi import APIRouter, Depends, Request
from mcp_tef_models.enums import SimilarityMethod
from mcp_tef_models.schemas import (
    DifferentiationRecommendationResponse,
    NormalizedTool,
    OverlapMatrixResponse,
    SimilarityAnalysisRequest,
    SimilarityAnalysisResponse,
)

from mcp_tef.config.settings import Settings, get_settings
from mcp_tef.services.embedding_service import EmbeddingService
from mcp_tef.services.llm_service import LLMService
from mcp_tef.services.mcp_loader import MCPLoaderService
from mcp_tef.services.recommendation_service import RecommendationService
from mcp_tef.services.similarity_service import SimilarityService

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_llm_model_config(
    settings: Settings,
) -> tuple[str, str, int, int]:
    """Get LLM configuration from settings.

    Args:
        settings: Application settings

    Returns:
        Tuple of (provider, model_name, timeout, max_retries)
    """
    return (
        settings.default_model.provider,
        settings.default_model.name,
        settings.default_model.timeout,
        settings.default_model.max_retries,
    )


def get_api_key_for_provider(provider: str, settings: Settings) -> str:
    """Get the appropriate API key for a given provider.

    Args:
        provider: Provider name (e.g., 'ollama', 'openrouter', 'openai', 'anthropic')
        settings: Application settings

    Returns:
        API key string (empty string for providers that don't require one like Ollama)
    """
    provider_map = {
        "openrouter": settings.openrouter_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "ollama": "",
    }
    key = provider_map.get(provider.lower())
    if key is None:
        logger.warning(f"Unknown provider '{provider}', using empty API key")
        return ""
    return key


def get_embedding_service(
    request: Request, settings: Settings = Depends(get_settings)
) -> EmbeddingService:
    """Dependency to create EmbeddingService instance.

    Uses cached instance from app.state if available (for testing),
    otherwise creates a new instance.

    Args:
        request: FastAPI request object
        settings: Application settings

    Returns:
        Configured EmbeddingService instance
    """
    # Use cached service if available (for testing to avoid rate limits)
    if hasattr(request.app.state, "embedding_service"):
        return request.app.state.embedding_service

    return EmbeddingService(
        model_type=cast(
            Literal["fastembed", "openai", "custom"],
            settings.embedding_model_type.value,
        ),
        model_name=settings.embedding_model_name,
        api_key=settings.openai_api_key,
        custom_api_url=settings.custom_embedding_api_url,
        timeout=settings.default_model.timeout,
    )


def get_similarity_service(
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    settings: Settings = Depends(get_settings),
) -> SimilarityService:
    """Dependency to create SimilarityService instance.

    Args:
        embedding_service: Configured embedding service
        settings: Application settings

    Returns:
        Configured SimilarityService instance
    """
    mcp_loader = MCPLoaderService(timeout=settings.mcp_server_timeout)
    return SimilarityService(
        embedding_service=embedding_service,
        mcp_loader_service=mcp_loader,
    )


@router.post(
    "/analyze",
    response_model=SimilarityAnalysisResponse,
    summary="Analyze tool similarity",
    description="Analyze similarity between multiple tools using configurable methods",
)
async def analyze_similarity(
    request: SimilarityAnalysisRequest,
    similarity_service: SimilarityService = Depends(get_similarity_service),
    settings: Settings = Depends(get_settings),
) -> SimilarityAnalysisResponse:
    """Analyze tool similarity and optionally generate recommendations.

    This endpoint accepts tools in five formats:
    - server_list: Array of MCP servers with embedded tools
    - tool_list: Array of tool definitions (direct)
    - url_list: Array of MCP server URLs to fetch tools from
    - server_ids: Array of MCP server IDs from database
    - server_names: Array of MCP server names from database

    Args:
        request: Similarity analysis request
        req: FastAPI request (for database access)
        similarity_service: Similarity analysis service
        settings: Application settings

    Returns:
        Similarity analysis response with matrix and optional recommendations

    Raises:
        ValidationError: If input is invalid
    """
    logger.info("Processing similarity analysis request")

    # Determine analysis method (validation already done by Pydantic)
    analysis_methods = request.analysis_methods or [SimilarityMethod.EMBEDDING]

    # Use first specified method (for now, only one method at a time)
    analysis_method = analysis_methods[0]
    logger.info(f"Using analysis method: {analysis_method.value}")

    # Override embedding service if custom model specified
    if request.embedding_model_name:
        logger.info(f"Using custom embedding model: {request.embedding_model_name}")

        # Use the validated model type from request, or fall back to settings default
        model_type = request.embedding_model_type
        if model_type is None:
            model_type = settings.embedding_model_type

        model_name = request.embedding_model_name

        # Create new embedding service with custom model
        custom_embedding_service = EmbeddingService(
            model_type=cast(Literal["fastembed", "openai", "custom"], model_type.value),
            model_name=model_name,
            api_key=settings.openai_api_key,
            custom_api_url=settings.custom_embedding_api_url,
            timeout=settings.default_model.timeout,
        )

        # Create new similarity service with custom embedding service
        similarity_service = SimilarityService(
            embedding_service=custom_embedding_service,
            mcp_loader_service=MCPLoaderService(timeout=settings.mcp_server_timeout),
        )

    # Extract and normalize tools
    tools = await similarity_service.extract_and_normalize_tools(
        server_configs=request.mcp_servers,
        tool_names=request.tool_names,
    )

    logger.info(f"Analyzing {len(tools)} tools")

    # Calculate similarity based on selected method
    if analysis_method == SimilarityMethod.DESCRIPTION_OVERLAP:
        # Use TF-IDF based description overlap
        desc_matrix = similarity_service.calculate_description_overlap(tools)
        full_matrix = None
    else:
        # Default: embedding-based similarity
        desc_matrix, full_matrix = await similarity_service.calculate_embedding_similarity(
            tools=tools,
            compute_full_similarity=request.compute_full_similarity,
        )

    # Use description-only matrix as primary similarity
    threshold = request.similarity_threshold
    matrix_data = similarity_service.build_similarity_matrix(
        tools=tools,
        embedding_matrix=desc_matrix,
        threshold=threshold,
    )

    # Initialize optional results
    recommendations: list[Any] | None = None

    # Process flagged pairs if recommendations requested
    flagged_pairs = matrix_data["flagged_pairs"]
    flagged_count = len(flagged_pairs)

    if flagged_count > 0 and request.include_recommendations:
        logger.info(f"Processing {flagged_count} flagged pairs for recommendations")

        # Get model configuration for recommendations (uses settings defaults)
        frontier_llm_config = get_llm_model_config(settings=settings)
        frontier_provider, frontier_model, frontier_timeout, frontier_retries = frontier_llm_config
        logger.info(
            f"Using FRONTIER model for recommendations: {frontier_provider}/{frontier_model}"
        )

        # Get the appropriate API key for the provider
        api_key = get_api_key_for_provider(frontier_provider, settings)

        # Create LLM service with frontier model for recommendations
        frontier_llm_service = LLMService(
            provider=frontier_provider,
            model=frontier_model,
            api_key=api_key,
            timeout=frontier_timeout,
            max_retries=frontier_retries,
            base_url=settings.get_base_url_for_provider(frontier_provider),
            settings=settings,
        )
        recommendation_service = RecommendationService(llm_service=frontier_llm_service)
        recommendations = []  # type: list[Any]

        # Build tool lookup by ID
        tool_lookup: dict[str, NormalizedTool] = {tool.id: tool for tool in tools}

        # Process each flagged pair with progress logging
        logger.info(f"Analyzing {flagged_count} pairs for recommendations...")
        for idx, pair in enumerate(flagged_pairs, start=1):
            tool_a = tool_lookup[pair["tool_a_id"]]
            tool_b = tool_lookup[pair["tool_b_id"]]
            similarity_score = pair["similarity_score"]

            # Generate recommendations for this pair
            logger.info(f"Processing pair {idx}/{flagged_count}: {tool_a.name} vs {tool_b.name}")
            recommendation = await recommendation_service.analyze_and_recommend(
                tool_a=tool_a,
                tool_b=tool_b,
                similarity_score=similarity_score,
            )
            recommendations.append(recommendation)

            # Log progress
            progress_pct = (idx / flagged_count) * 100
            logger.info(
                f"Progress: {idx}/{flagged_count} pairs complete ({progress_pct:.1f}%)",
                completed_pairs=idx,
                total_pairs=flagged_count,
                progress_percentage=f"{progress_pct:.1f}%",
            )

    # Create response
    response_data: dict[str, Any] = {
        **matrix_data,
        "recommendations": recommendations,
    }

    logger.info(f"Analysis complete: {flagged_count} pairs flagged above threshold {threshold}")

    return SimilarityAnalysisResponse.model_validate(response_data)  # type: ignore[arg-type]


@router.post(
    "/overlap-matrix",
    response_model=OverlapMatrixResponse,
    summary="Generate capability overlap matrix",
    description=(
        "Generate a capability overlap matrix showing functional overlap in multiple dimensions"
    ),
)
async def generate_overlap_matrix(
    request: SimilarityAnalysisRequest,
    similarity_service: SimilarityService = Depends(get_similarity_service),
) -> OverlapMatrixResponse:
    """Generate capability overlap matrix with dimension breakdown.

    Args:
        request: Similarity analysis request
        req: FastAPI request (for database access)
        similarity_service: Similarity analysis service

    Returns:
        Overlap matrix response with dimension weights

    Raises:
        ValidationError: If input is invalid
    """
    logger.info("Generating overlap matrix")

    # Extract and normalize tools

    tools = await similarity_service.extract_and_normalize_tools(
        server_configs=request.mcp_servers,
    )

    logger.info(f"Generating overlap matrix for {len(tools)} tools")

    # Calculate semantic similarity (embedding-based)
    semantic_matrix, _ = await similarity_service.calculate_embedding_similarity(
        tools=tools,
        compute_full_similarity=False,
    )

    # Calculate description overlap (TF-IDF)
    description_matrix = similarity_service.calculate_description_overlap(tools)

    # Calculate parameter overlap (Jaccard)
    parameter_matrix = similarity_service.calculate_parameter_overlap_matrix(tools)

    # Build overlap matrix with weighted dimensions
    overlap_data = similarity_service.calculate_overlap_matrix(
        tools=tools,
        semantic_matrix=semantic_matrix,
        description_matrix=description_matrix,
        parameter_matrix=parameter_matrix,
    )

    return OverlapMatrixResponse(**overlap_data)


@router.post(
    "/recommendations",
    response_model=DifferentiationRecommendationResponse,
    summary="Get differentiation recommendations",
    description="Analyze tool pair and generate actionable differentiation recommendations",
)
async def get_recommendations(
    request: SimilarityAnalysisRequest,
    settings: Settings = Depends(get_settings),
    similarity_service: SimilarityService = Depends(get_similarity_service),
) -> DifferentiationRecommendationResponse:
    """Get differentiation recommendations for a tool pair.

    Args:
        request: Similarity analysis request (must contain exactly 2 tools)
        settings: Application settings
        similarity_service: Similarity analysis service

    Returns:
        Differentiation recommendations
    """
    logger.info("Generating differentiation recommendations")

    # Extract and normalize tools
    tools = await similarity_service.extract_and_normalize_tools(
        server_configs=request.mcp_servers,
        tool_names=request.tool_names,
    )

    if len(tools) != 2:
        from mcp_tef.api.errors import ValidationError

        raise ValidationError(f"Recommendations require exactly 2 tools, got {len(tools)}")

    # Calculate similarity
    desc_matrix, _ = await similarity_service.calculate_embedding_similarity(
        tools=tools,
        compute_full_similarity=False,
    )
    similarity_score = float(desc_matrix[0][1])

    # Get frontier model configuration from settings
    (
        frontier_provider,
        frontier_model,
        frontier_timeout,
        frontier_retries,
    ) = get_llm_model_config(settings=settings)
    logger.info(f"Using FRONTIER model for recommendations: {frontier_provider}/{frontier_model}")
    frontier_llm_service = LLMService(
        provider=frontier_provider,
        model=frontier_model,
        api_key=get_api_key_for_provider(frontier_provider, settings),
        timeout=frontier_timeout,
        max_retries=frontier_retries,
        base_url=settings.get_base_url_for_provider(frontier_provider),
        settings=settings,
    )

    # Generate recommendations using frontier model
    recommendation_service = RecommendationService(llm_service=frontier_llm_service)
    recommendation = await recommendation_service.analyze_and_recommend(
        tool_a=tools[0],
        tool_b=tools[1],
        similarity_score=similarity_score,
    )

    return DifferentiationRecommendationResponse(
        **recommendation.model_dump(),
        generated_at=datetime.now(UTC).isoformat(),
    )
