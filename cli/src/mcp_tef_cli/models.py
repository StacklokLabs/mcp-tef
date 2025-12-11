"""Vendored API models for mcp-tef CLI.

This module contains minimal Pydantic models for interacting with the mcp-tef API.
These models are vendored (copied) from the main mcp-tef package to avoid
requiring the full server as a dependency.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "HealthResponse",
    "ServerInfo",
    "EvaluationDimensionResult",
    "EvaluationResult",
    "ToolQualityResult",
    "ToolQualityResponse",
    # Test case models
    "TestCaseCreate",
    "TestCaseResponse",
    "PaginatedTestCaseResponse",
    "ToolDefinition",
    # Test run models
    "ModelSettingsCreate",
    "ModelSettingsResponse",
    "TestRunExecuteRequest",
    "ToolEnrichedResponse",
    "TestRunResponse",
    "PaginatedTestRunResponse",
    # Similarity models
    "ToolPair",
    "SimilarityMatrixResponse",
    "DifferentiationIssue",
    "RecommendationItem",
    "DifferentiationRecommendation",
    "DifferentiationRecommendationResponse",
    "OverlapMatrixResponse",
    "SimilarityAnalysisResponse",
]


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


# =============================================================================
# Test Case Models
# =============================================================================


class ToolDefinition(BaseModel):
    """Definition of a tool available from an MCP server."""

    name: str = Field(..., description="Tool name")
    description: str | None = Field(default=None, description="Tool description")


class TestCaseCreate(BaseModel):
    """Request model for creating a test case."""

    name: str = Field(..., description="Descriptive name for the test case")
    query: str = Field(..., description="User query to evaluate")
    expected_mcp_server_url: str | None = Field(
        default=None, description="Expected MCP server URL (null for negative tests)"
    )
    expected_tool_name: str | None = Field(
        default=None, description="Expected tool name (null for negative tests)"
    )
    expected_parameters: dict | None = Field(
        default=None, description="Expected parameters as JSON object"
    )
    available_mcp_servers: list[str] = Field(
        ..., description="MCP server URLs available for selection", min_length=1
    )

    @model_validator(mode="after")
    def validate_expected_tool_fields(self) -> "TestCaseCreate":
        """Validate cross-field constraints for expected tool configuration."""
        # expected_server and expected_tool must both be present or both absent
        if (self.expected_mcp_server_url is None) != (self.expected_tool_name is None):
            raise ValueError(
                "expected_mcp_server_url and expected_tool_name must both be provided "
                "or both omitted"
            )

        # expected_server must be in available_mcp_servers
        if (
            self.expected_mcp_server_url
            and self.expected_mcp_server_url not in self.available_mcp_servers
        ):
            raise ValueError(
                f"expected_mcp_server_url '{self.expected_mcp_server_url}' "
                "must be in available_mcp_servers"
            )

        # expected_parameters requires expected_tool_name
        if self.expected_parameters and not self.expected_tool_name:
            raise ValueError("expected_parameters requires expected_tool_name to be set")

        return self


class TestCaseResponse(BaseModel):
    """Response model for test case."""

    id: str = Field(..., description="Test case UUID")
    name: str = Field(..., description="Test case name")
    query: str = Field(..., description="User query")
    expected_mcp_server_url: str | None = Field(default=None, description="Expected MCP server URL")
    expected_tool_name: str | None = Field(default=None, description="Expected tool name")
    expected_parameters: dict | None = Field(default=None, description="Expected parameters")
    available_mcp_servers: list[str] = Field(..., description="Available MCP servers")
    available_tools: dict[str, list[ToolDefinition]] | None = Field(
        default=None, description="Available tools by server URL"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class PaginatedTestCaseResponse(BaseModel):
    """Paginated test case response."""

    items: list[TestCaseResponse] = Field(..., description="Test cases")
    total: int = Field(..., description="Total number of test cases")
    offset: int = Field(..., description="Offset for pagination")
    limit: int = Field(..., description="Limit for pagination")


# =============================================================================
# Test Run Models
# =============================================================================


class ModelSettingsCreate(BaseModel):
    """Model configuration for test execution."""

    provider: str = Field(..., description="LLM provider name")
    model: str = Field(..., description="Model identifier")
    timeout: int = Field(default=30, description="Model timeout in seconds")
    temperature: float = Field(default=0.4, description="Model temperature")
    max_retries: int = Field(default=3, description="Maximum retries on failure")
    base_url: str | None = Field(default=None, description="Custom base URL")


class ModelSettingsResponse(BaseModel):
    """Model settings response from API."""

    id: str | None = Field(default=None, description="Model settings ID")
    provider: str = Field(..., description="LLM provider name")
    model: str = Field(..., description="Model identifier")
    timeout: int = Field(default=30, description="Model timeout in seconds")
    temperature: float = Field(default=0.4, description="Model temperature")
    max_retries: int = Field(default=3, description="Maximum retries on failure")
    base_url: str | None = Field(default=None, description="Custom base URL")


class TestRunExecuteRequest(BaseModel):
    """Request model for executing a test run."""

    model_settings: ModelSettingsCreate = Field(..., description="Model configuration")


class ToolEnrichedResponse(BaseModel):
    """Tool information with parameters."""

    id: str | None = Field(default=None, description="Tool ID")
    name: str = Field(..., description="Tool name")
    mcp_server_url: str = Field(..., description="MCP server URL")
    parameters: dict | None = Field(default=None, description="Tool parameters")


class TestRunResponse(BaseModel):
    """Response model for test run."""

    id: str = Field(..., description="Test run UUID")
    test_case_id: str = Field(..., description="Associated test case ID")
    model_settings: ModelSettingsResponse | None = Field(
        default=None, description="Model settings used"
    )
    status: str = Field(..., description="Status: pending, running, completed, failed")
    llm_response_raw: str | None = Field(default=None, description="Raw LLM response")
    selected_tool: ToolEnrichedResponse | None = Field(
        default=None, description="Tool selected by LLM"
    )
    expected_tool: ToolEnrichedResponse | None = Field(
        default=None, description="Expected tool from test case"
    )
    extracted_parameters: dict | None = Field(
        default=None, description="Parameters extracted from LLM response"
    )
    parameter_correctness: float | None = Field(
        default=None, description="Parameter accuracy score"
    )
    llm_confidence: str | None = Field(default=None, description="LLM confidence level: high, low")
    confidence_score: str | None = Field(
        default=None, description="Confidence score: robust, needs_clarity, misleading"
    )
    classification: str | None = Field(default=None, description="Classification: TP, FP, TN, FN")
    execution_time_ms: int | None = Field(default=None, description="Execution time in ms")
    error_message: str | None = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(..., description="Creation timestamp")
    completed_at: datetime | None = Field(default=None, description="Completion timestamp")


class PaginatedTestRunResponse(BaseModel):
    """Paginated test run response."""

    items: list[TestRunResponse] = Field(..., description="List of test runs")
    total: int = Field(..., description="Total number of test runs")
    offset: int = Field(..., description="Offset for pagination")
    limit: int = Field(..., description="Limit for pagination")


# =============================================================================
# Similarity Models
# =============================================================================


class ToolPair(BaseModel):
    """Tool pair with similarity score."""

    tool_a_id: str = Field(..., description="First tool ID")
    tool_b_id: str = Field(..., description="Second tool ID")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Similarity score")


class SimilarityMatrixResponse(BaseModel):
    """Response for similarity matrix."""

    tool_ids: list[str] = Field(..., description="Ordered list of tool IDs")
    matrix: list[list[float]] = Field(..., description="2D similarity matrix")
    threshold: float = Field(..., description="Threshold used for flagging")
    flagged_pairs: list[ToolPair] = Field(..., description="Pairs exceeding threshold")
    generated_at: str = Field(..., description="Generation timestamp (ISO 8601)")


class DifferentiationIssue(BaseModel):
    """Issue identified in tool pair analysis."""

    issue_type: str = Field(..., description="Issue type identifier")
    description: str = Field(..., description="Human-readable description")
    tool_a_id: str = Field(..., description="First tool ID")
    tool_b_id: str = Field(..., description="Second tool ID")
    evidence: dict[str, Any] = Field(default_factory=dict, description="Supporting evidence")


class RecommendationItem(BaseModel):
    """Individual actionable recommendation."""

    issue: str = Field(..., description="Issue this addresses")
    tool_id: str | None = Field(None, description="Tool to modify")
    recommendation: str = Field(..., description="Specific action")
    rationale: str = Field(..., description="Why this matters")
    priority: str = Field(..., description="Priority: high, medium, low")
    revised_description: str | None = Field(None, description="Improved description")
    apply_commands: list[str] | None = Field(None, description="Commands to apply")


class DifferentiationRecommendation(BaseModel):
    """Recommendation for improving tool differentiation."""

    tool_pair: list[str] = Field(..., description="[tool_a_id, tool_b_id]")
    similarity_score: float = Field(..., description="Similarity score")
    issues: list[DifferentiationIssue] = Field(..., description="Identified issues")
    recommendations: list[RecommendationItem] = Field(..., description="Recommendations")


class DifferentiationRecommendationResponse(DifferentiationRecommendation):
    """Response for recommendations endpoint."""

    generated_at: str = Field(..., description="Generation timestamp")


class OverlapMatrixResponse(BaseModel):
    """Response for capability overlap matrix."""

    tool_ids: list[str] = Field(..., description="Ordered list of tool IDs")
    matrix: list[list[float]] = Field(..., description="2D overlap matrix")
    dimensions: dict[str, float] = Field(..., description="Dimension weights")
    generated_at: str = Field(..., description="Generation timestamp")


class SimilarityAnalysisResponse(SimilarityMatrixResponse):
    """Response for full similarity analysis."""

    recommendations: list[DifferentiationRecommendation] | None = Field(
        None, description="Recommendations if requested"
    )
