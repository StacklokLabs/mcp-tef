"""CLI-specific models and re-exports from mcp-tef-models.

This module contains CLI-specific models and re-exports shared models from
mcp_tef_models for convenience. All shared models should be imported from
mcp_tef_models directly.
"""

# Re-export shared models from mcp_tef_models for convenience
from mcp_tef_models.schemas import (  # noqa: F401
    DifferentiationIssue,
    DifferentiationRecommendation,
    DifferentiationRecommendationResponse,
    MCPServerConfig,
    ModelSettingsCreate,
    ModelSettingsResponse,
    OverlapMatrixResponse,
    PaginatedTestCaseResponse,
    PaginatedTestRunResponse,
    RecommendationItem,
    SimilarityAnalysisResponse,
    SimilarityMatrixResponse,
    TestCaseCreate,
    TestCaseResponse,
    TestRunExecuteRequest,
    TestRunResponse,
    ToolDefinition,
    ToolPair,
)
from pydantic import BaseModel, Field

__all__ = [
    # CLI-specific models
    "HealthResponse",
    "ServerInfo",
    "EvaluationDimensionResult",
    "EvaluationResult",
    "ToolQualityResult",
    "ToolQualityResponse",
    # Re-exported shared models
    "DifferentiationIssue",
    "DifferentiationRecommendation",
    "DifferentiationRecommendationResponse",
    "MCPServerConfig",
    "ModelSettingsCreate",
    "ModelSettingsResponse",
    "OverlapMatrixResponse",
    "PaginatedTestCaseResponse",
    "PaginatedTestRunResponse",
    "RecommendationItem",
    "SimilarityAnalysisResponse",
    "SimilarityMatrixResponse",
    "TestCaseCreate",
    "TestCaseResponse",
    "TestRunExecuteRequest",
    "TestRunResponse",
    "ToolDefinition",
    "ToolPair",
]


# =============================================================================
# CLI-Specific Models
# =============================================================================


class HealthResponse(BaseModel):
    """Response schema for health check endpoint."""

    status: str = Field(..., description="Health status (healthy/unhealthy)")


class ServerInfo(BaseModel):
    """Response schema for server information endpoint."""

    name: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    status: str = Field(..., description="Service status")


class EvaluationDimensionResult(BaseModel):
    """Result of evaluation along a single dimension (clarity, completeness, conciseness)."""

    score: int = Field(..., description="A score from 1 to 10 for this dimension")
    explanation: str = Field(..., description="Explanation of the reasoning for the given score")


class EvaluationResult(BaseModel):
    """Output model for the tool description evaluation."""

    clarity: EvaluationDimensionResult = Field(
        ..., description="Evaluation of the clarity of the tool description"
    )
    completeness: EvaluationDimensionResult = Field(
        ..., description="Evaluation of the completeness of the tool description"
    )
    conciseness: EvaluationDimensionResult = Field(
        ..., description="Evaluation of the conciseness of the tool description"
    )
    suggested_description: str | None = Field(
        default=None,
        description="Suggested tool description (optional)",
    )


class ToolQualityResult(BaseModel):
    """Result of quality evaluation for a single tool."""

    tool_name: str = Field(..., description="Tool name")
    tool_description: str = Field(..., description="Original tool description")
    evaluation_result: EvaluationResult = Field(..., description="Result of the tool evaluation")


class ToolQualityResponse(BaseModel):
    """Response from the tool quality evaluation endpoint."""

    results: list[ToolQualityResult] = Field(..., description="Tool quality results")
    errors: list[str] | None = Field(
        default=None, description="Errors encountered during evaluation"
    )
