"""Pydantic models for API request/response validation.

This module re-exports models from mcp_tef_models for backward compatibility.
New code should import directly from mcp_tef_models.
"""

# Re-export all schemas from mcp_tef_models for backward compatibility
from mcp_tef_models.schemas import (  # noqa: F401
    DifferentiationIssue,
    DifferentiationRecommendation,
    DifferentiationRecommendationResponse,
    MCPServer,
    MCPServerConfig,
    MCPServerToolsResponse,
    MetricsSummaryResponse,
    ModelSettingsCreate,
    ModelSettingsResponse,
    NormalizedTool,
    OverlapMatrixResponse,
    PaginatedTestCaseResponse,
    PaginatedTestRunResponse,
    RecommendationItem,
    SimilarityAnalysisRequest,
    SimilarityAnalysisResponse,
    SimilarityScore,
    TestCaseCreate,
    TestCaseResponse,
    TestRunExecuteRequest,
    TestRunResponse,
    ToolDefinition,
    ToolDefinitionCreate,
    ToolDefinitionResponse,
    ToolEnrichedResponse,
    ToolPair,
)

__all__ = [
    "DifferentiationIssue",
    "DifferentiationRecommendation",
    "DifferentiationRecommendationResponse",
    "MCPServer",
    "MCPServerConfig",
    "MCPServerToolsResponse",
    "MetricsSummaryResponse",
    "ModelSettingsCreate",
    "ModelSettingsResponse",
    "NormalizedTool",
    "OverlapMatrixResponse",
    "PaginatedTestCaseResponse",
    "PaginatedTestRunResponse",
    "RecommendationItem",
    "SimilarityAnalysisRequest",
    "SimilarityAnalysisResponse",
    "SimilarityScore",
    "TestCaseCreate",
    "TestCaseResponse",
    "TestRunExecuteRequest",
    "TestRunResponse",
    "ToolDefinition",
    "ToolDefinitionCreate",
    "ToolDefinitionResponse",
    "ToolEnrichedResponse",
    "ToolPair",
]
