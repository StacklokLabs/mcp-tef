"""Pydantic models for API request/response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from mcp_tef.models.enums import EmbeddingModelType, SimilarityMethod

# MCP Server Configuration Model


class MCPServerConfig(BaseModel):
    """MCP server configuration with validation."""

    url: str = Field(
        ...,
        min_length=1,
        pattern=r"^https?://",
        description="Server URL (must be http or https)",
    )
    transport: str = Field(
        default="streamable-http",
        pattern=r"^(sse|streamable-http)$",
        description="Transport type: 'sse' or 'streamable-http'",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "http://localhost:3000/mcp",
                "transport": "streamable-http",
            }
        }
    )


# Model Settings Models


class ModelSettingsCreate(BaseModel):
    """Request schema for model configuration (runtime only, not persisted with API key)."""

    provider: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="LLM provider name (e.g., 'openai', 'anthropic')",
    )
    model: str = Field(..., min_length=1, max_length=100, description="Model name (e.g., 'gpt-4')")
    timeout: int = Field(30, gt=0, le=300, description="Request timeout in seconds")
    temperature: float = Field(0.4, ge=0.0, le=2.0, description="Sampling temperature")
    max_retries: int = Field(3, ge=0, le=10, description="Maximum retry attempts")
    base_url: str | None = Field(
        None,
        description="Base URL for API endpoint (required for ollama, openrouter, etc.)",
    )
    system_prompt: str | None = Field(None, description="System prompt for the LLM")


class ModelSettingsResponse(BaseModel):
    """Response schema for model settings (persisted configuration without API key)."""

    id: str = Field(..., description="Model settings ID")
    provider: str = Field(..., description="LLM provider name")
    model: str = Field(..., description="Model name")
    timeout: int = Field(..., description="Request timeout in seconds")
    temperature: float = Field(..., description="Sampling temperature")
    max_retries: int = Field(..., description="Maximum retry attempts")
    base_url: str | None = Field(None, description="Base URL for API endpoint")
    system_prompt: str | None = Field(None, description="System prompt for the LLM")
    created_at: datetime = Field(..., description="Creation timestamp")

    model_config = ConfigDict(from_attributes=True)


class TestRunExecuteRequest(BaseModel):
    """Request schema for executing a test case with runtime model configuration."""

    model_settings: ModelSettingsCreate = Field(
        ..., description="LLM configuration for this test run"
    )


# Tool Definition Models


class ToolDefinitionCreate(BaseModel):
    """Request schema for creating a tool definition."""

    name: str = Field(
        ...,
        min_length=1,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Tool name (alphanumeric with underscores/hyphens)",
    )
    description: str = Field(..., min_length=1, description="Tool description")
    input_schema: dict[str, Any] = Field(..., description="JSON Schema for tool parameters")
    output_schema: dict[str, Any] | None = Field(
        None, description="Optional JSON Schema for output"
    )
    mcp_server_url: str = Field(..., description="MCP server url that provides this tool")
    test_run_id: str = Field(..., description="Test run ID that ingested this tool")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "get_weather",
                "description": "Get current weather for a location",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                        "units": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "default": "celsius",
                        },
                    },
                    "required": ["location"],
                },
            }
        }
    )


class ToolDefinitionResponse(BaseModel):
    """Response schema for tool definition."""

    id: str = Field(..., description="Tool definition ID")
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    input_schema: dict[str, Any] = Field(..., description="JSON Schema for tool parameters")
    output_schema: dict[str, Any] | None = Field(
        None, description="Optional JSON Schema for output"
    )
    mcp_server_url: str = Field(..., description="MCP server url that provides this tool")
    test_run_id: str = Field(..., description="Test run ID that ingested this tool")
    created_at: datetime = Field(..., description="Creation timestamp")

    model_config = ConfigDict(from_attributes=True)


class MCPServerToolsResponse(BaseModel):
    """Response schema for tools from a specific MCP server."""

    tools: list[ToolDefinition] = Field(..., description="Tools from this MCP server")
    count: int = Field(..., description="Number of tools")


# Test Case Models


class TestCaseCreate(BaseModel):
    """Request schema for creating a test case."""

    name: str = Field(..., min_length=1, description="Test case name")
    query: str = Field(..., min_length=1, description="User query to evaluate")
    expected_mcp_server_url: str | None = Field(
        None,
        min_length=1,
        description="Expected MCP server url (nullable if no tool expected)",
    )
    expected_tool_name: str | None = Field(
        None,
        min_length=1,
        description="Expected tool name (nullable if no tool expected)",
    )
    expected_parameters: dict[str, Any] | None = Field(
        None, description="Expected parameter values"
    )
    available_mcp_servers: list[MCPServerConfig] = Field(
        ...,
        min_length=1,
        description="List of MCP server configurations",
    )

    @model_validator(mode="after")
    def validate_expected_tool_fields(self) -> TestCaseCreate:
        """Ensure expected_mcp_server_url and expected_tool_name are both null or both non-null."""
        server_url = self.expected_mcp_server_url
        tool = self.expected_tool_name
        if (server_url is None) != (tool is None):
            raise ValueError(
                "expected_mcp_server_url and expected_tool_name must both be "
                "null or both be non-null"
            )
        if server_url:
            # Validate expected server URL exists in available_mcp_servers
            available_urls = [server.url for server in self.available_mcp_servers]
            if server_url not in available_urls:
                raise ValueError(
                    f"expected_mcp_server_url '{server_url}' must be in available_mcp_servers"
                )
        return self


class TestCaseResponse(BaseModel):
    """Response schema for test case."""

    id: str = Field(..., description="Test case ID")
    name: str = Field(..., description="Test case name")
    query: str = Field(..., description="User query to evaluate")
    expected_mcp_server_url: str | None = Field(None, description="Expected MCP server url")
    expected_tool_name: str | None = Field(None, description="Expected tool name")
    expected_parameters: dict[str, Any] | None = Field(None, description="Expected parameters")
    available_mcp_servers: list[MCPServerConfig] = Field(
        ..., description="List of MCP server configurations"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    available_tools: dict[str, list[ToolDefinition]] | None = Field(
        default=None,
        description="Tools for the available MCP servers",
    )

    model_config = ConfigDict(from_attributes=True)


class PaginatedTestCaseResponse(BaseModel):
    """Paginated response for test case list."""

    items: list[TestCaseResponse] = Field(..., description="List of test cases")
    total: int = Field(..., description="Total number of test cases")
    offset: int = Field(0, description="Pagination offset")
    limit: int = Field(100, description="Pagination limit")


# Test Run Models


class ToolEnrichedResponse(BaseModel):
    """Enriched tool response with MCP server information."""

    id: str | None = Field(default=None, description="Tool ID (None for 'expected tools')")
    name: str = Field(..., description="Tool name")
    mcp_server_url: str = Field(..., description="MCP server url")
    parameters: dict[str, Any] | None = Field(
        None, description="Tool parameters (extracted or expected)"
    )

    model_config = ConfigDict(from_attributes=True)


class TestRunResponse(BaseModel):
    """Response schema for test run."""

    id: str = Field(..., description="Test run ID")
    test_case_id: str = Field(..., description="Test case ID")
    model_settings: ModelSettingsResponse | None = Field(
        None, description="Model configuration used for this run (without API key)"
    )
    status: str = Field(..., description="Test run status (pending/running/completed/failed)")
    llm_response_raw: str | None = Field(None, description="Raw LLM response JSON")
    selected_tool: ToolEnrichedResponse | None = Field(
        None, description="Tool selected by LLM with MCP server info and parameters"
    )
    expected_tool: ToolEnrichedResponse | None = Field(
        None, description="Expected tool with MCP server info and parameters"
    )
    extracted_parameters: dict | None = Field(
        None, description="Parameters extracted from LLM response (JSON)"
    )
    llm_confidence: str | None = Field(None, description="LLM confidence level (high/low)")
    parameter_correctness: float | None = Field(
        None, description="Parameter correctness score (0-10)"
    )
    confidence_score: str | None = Field(
        None,
        description=(
            "Confidence score description (robust description/needs clarity/misleading description)"
        ),
    )
    classification: str | None = Field(None, description="Result classification (TP/FP/TN/FN)")
    execution_time_ms: int | None = Field(None, description="Execution time in milliseconds")
    error_message: str | None = Field(None, description="Error message if failed")
    created_at: datetime = Field(..., description="Creation timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")

    tools: list[ToolEnrichedResponse] = Field(
        default_factory=list, description="All tools available in test case MCP servers"
    )

    model_config = ConfigDict(from_attributes=True)


class PaginatedTestRunResponse(BaseModel):
    """Response schema for multiple test runs."""

    items: list[TestRunResponse] = Field(..., description="List of test runs")
    total: int = Field(..., description="Total number of test runs")
    offset: int = Field(0, description="Pagination offset")
    limit: int = Field(100, description="Pagination limit")


# Metrics Models


class MetricsSummaryResponse(BaseModel):
    """Response schema for aggregated metrics summary."""

    total_tests: int = Field(..., ge=0, description="Total number of evaluated test runs")
    true_positives: int = Field(..., ge=0, description="Count of TP classifications")
    false_positives: int = Field(..., ge=0, description="Count of FP classifications")
    true_negatives: int = Field(..., ge=0, description="Count of TN classifications")
    false_negatives: int = Field(..., ge=0, description="Count of FN classifications")
    precision: float = Field(
        ..., ge=0.0, le=1.0, description="Precision: TP / (TP + FP) or 0.0 if undefined"
    )
    recall: float = Field(
        ..., ge=0.0, le=1.0, description="Recall: TP / (TP + FN) or 0.0 if undefined"
    )
    f1_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="F1 Score: 2 * (Precision * Recall) / (Precision + Recall) or 0.0 if undefined",
    )
    parameter_accuracy: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Average parameter correctness (0-10 scale) or 0.0 if no parameter data",
    )
    average_execution_time_ms: float = Field(
        ..., ge=0.0, description="Average execution time in milliseconds"
    )
    robust_description_count: int = Field(
        ..., ge=0, description="Count of test runs with robust descriptions"
    )
    needs_clarity_count: int = Field(..., ge=0, description="Count of test runs that need clarity")
    misleading_description_count: int = Field(
        ..., ge=0, description="Count of test runs with misleading descriptions"
    )
    test_run_ids: list[str] = Field(
        ..., description="List of test run IDs included in this summary"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_tests": 10,
                "true_positives": 8,
                "false_positives": 1,
                "true_negatives": 0,
                "false_negatives": 1,
                "precision": 0.889,
                "recall": 0.889,
                "f1_score": 0.889,
                "parameter_accuracy": 9.5,
                "average_execution_time_ms": 1320.5,
                "robust_description_count": 8,
                "needs_clarity_count": 1,
                "misleading_description_count": 1,
                "test_run_ids": [
                    "550e8400-e29b-41d4-a716-446655440000",
                    "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                ],
            }
        }
    )


# Similarity Analysis Models


class MCPServer(BaseModel):
    """MCP server structure containing multiple tools."""

    name: str = Field(..., min_length=1, description="Server name")
    description: str = Field(..., description="Server description")
    url: str | None = Field(None, description="Server URL (optional)")
    tools: list[ToolDefinition] = Field(..., description="Array of tools in this server")


class ToolDefinition(BaseModel):
    """Tool definition in request format (simpler than database format)."""

    name: str = Field(..., min_length=1, description="Tool name")
    description: str = Field(..., min_length=1, description="Tool description")
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Full JSON Schema for tool parameters (may include $defs and $ref)",
    )
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Parameter names to descriptions (extracted from input_schema for convenience). "
            "Use input_schema for full schema with types and validation."
        ),
    )


class NormalizedTool(BaseModel):
    """Internal model for normalized tool used in similarity analysis."""

    id: str = Field(..., description="Unique tool identifier (format: server:tool_name)")
    name: str = Field(..., min_length=1, description="Tool name")
    description: str = Field(..., min_length=1, description="Tool description")
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Full JSON Schema for tool parameters (may include $defs and $ref)",
    )
    parameters: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Parameter names to descriptions (extracted from input_schema for convenience). "
            "Use input_schema for full schema with types and validation."
        ),
    )
    server_url: str | None = Field(None, description="MCP server url")


class SimilarityAnalysisRequest(BaseModel):
    """Request schema for similarity analysis."""

    mcp_servers: list[MCPServerConfig] = Field(
        min_length=1,
        description="List of MCP server configurations to analyze",
    )
    tool_names: list[str] | None = Field(
        None,
        description=(
            "Optional list of tool names to filter. If provided, only tools with matching names "
            "will be included in the analysis. Useful when a server exposes many tools but you "
            "want to compare specific ones."
        ),
    )

    # Configuration
    embedding_model: str | None = Field(
        None,
        description=(
            "Embedding model identifier. Format: 'modelname' or 'type:modelname' "
            "(e.g., 'fastembed:BAAI/bge-small-en-v1.5' or 'openai:text-embedding-3-small'). "
            "Supported types: fastembed, openai"
        ),
    )
    embedding_model_type: EmbeddingModelType | None = Field(
        None,
        description="Embedding model type (extracted from embedding_model if not specified)",
    )
    embedding_model_name: str | None = Field(
        None,
        description="Embedding model name (extracted from embedding_model if not specified)",
    )
    llm_model: str | None = Field(
        None,
        description=(
            "LLM model for confusion testing and recommendations (uses default if not specified). "
            "Deprecated: Use small_model_id or frontier_model_id instead."
        ),
    )
    small_model_id: str | None = Field(
        None,
        description=(
            "Model ID (from database) to use for simple language tasks "
            "(tool selection, confusion testing). If not specified, system will "
            "try to find a model with class='small' in the database."
        ),
    )
    frontier_model_id: str | None = Field(
        None,
        description=(
            "Model ID (from database) to use for complex reasoning tasks "
            "(recommendations, generation). If not specified, system will "
            "try to find a model with class='frontier' in the database."
        ),
    )
    similarity_threshold: float = Field(
        0.85,
        ge=0.0,
        le=1.0,
        description="Threshold for flagging high similarity",
    )
    analysis_methods: list[SimilarityMethod] | None = Field(
        None,
        description="Analysis methods to use (default: embedding)",
    )
    compute_full_similarity: bool = Field(
        False,
        description=(
            "Whether to compute full similarity (including parameters) "
            "in addition to description-only"
        ),
    )
    include_recommendations: bool = Field(
        False, description="Whether to generate differentiation recommendations"
    )

    @field_validator("analysis_methods", mode="before")
    @classmethod
    def validate_analysis_methods(
        cls, v: list[str | SimilarityMethod] | None
    ) -> list[SimilarityMethod] | None:
        """Validate and convert analysis methods to enum values.

        Args:
            v: List of analysis method strings or enums

        Returns:
            List of SimilarityMethod enums or None

        Raises:
            ValueError: If any method is not supported
        """
        if v is None:
            return None

        result = []
        for method in v:
            if isinstance(method, SimilarityMethod):
                result.append(method)
            elif isinstance(method, str):
                try:
                    result.append(SimilarityMethod(method))
                except ValueError:
                    valid_methods = ", ".join([m.value for m in SimilarityMethod])
                    raise ValueError(
                        f"Unsupported analysis method: {method}. Valid methods: {valid_methods}"
                    ) from None
            else:
                raise ValueError(f"Invalid analysis method type: {type(method)}")
        return result

    @model_validator(mode="after")
    def parse_embedding_model(self) -> SimilarityAnalysisRequest:
        """Parse embedding_model string into type and name components.

        Supports format: "modelname" or "type:modelname"
        If embedding_model_type/name are already set, they take precedence.

        Returns:
            Self with parsed embedding_model_type and embedding_model_name

        Raises:
            ValueError: If model type is not supported
        """
        if not self.embedding_model:
            return self

        # If type and name already explicitly set, use those
        if self.embedding_model_type and self.embedding_model_name:
            return self

        # Parse the embedding_model string
        if ":" in self.embedding_model:
            model_type_str, model_name = self.embedding_model.split(":", 1)
            try:
                model_type = EmbeddingModelType(model_type_str)
            except ValueError:
                valid_types = ", ".join([t.value for t in EmbeddingModelType])
                raise ValueError(
                    f"Unsupported embedding model type: {model_type_str}. "
                    f"Valid types: {valid_types}"
                ) from None

            self.embedding_model_type = model_type
            self.embedding_model_name = model_name
        else:
            # Just a model name without type prefix
            self.embedding_model_name = self.embedding_model

        return self


class SimilarityScore(BaseModel):
    """Pairwise similarity score between two tools."""

    tool_a_id: str = Field(..., description="First tool ID")
    tool_b_id: str = Field(..., description="Second tool ID")
    similarity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Description-only similarity score (primary)"
    )
    full_similarity_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Optional full similarity including parameters",
    )
    method: str = Field(
        ...,
        description=(
            "Analysis method: embedding, description_overlap, purpose_comparison, llm_similarity"
        ),
    )
    flagged: bool = Field(..., description="Whether description-only similarity exceeds threshold")


class ToolPair(BaseModel):
    """Tool pair with similarity score."""

    tool_a_id: str = Field(..., description="First tool ID")
    tool_b_id: str = Field(..., description="Second tool ID")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Similarity score")


class SimilarityMatrixResponse(BaseModel):
    """Response schema for similarity matrix."""

    tool_ids: list[str] = Field(..., description="Ordered list of tool IDs (matrix rows/columns)")
    matrix: list[list[float]] = Field(
        ..., description="2D similarity matrix (symmetric, diagonal = 1.0)"
    )
    threshold: float = Field(..., description="Threshold used for flagging")
    flagged_pairs: list[ToolPair] = Field(..., description="Tool pairs exceeding threshold")
    generated_at: str = Field(..., description="Timestamp of generation (ISO 8601)")


class DifferentiationIssue(BaseModel):
    """Specific issue identified in tool pair analysis."""

    issue_type: str = Field(
        ...,
        description=(
            "Issue type: scope_clarity, example_distinctiveness, "
            "parameter_uniqueness, naming_clarity, terminology_overlap"
        ),
    )
    description: str = Field(..., description="Human-readable description of issue")
    tool_a_id: str = Field(..., description="First tool ID")
    tool_b_id: str = Field(..., description="Second tool ID")
    evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="Supporting evidence (e.g., overlapping terms, similar parameters)",
    )


class RecommendationItem(BaseModel):
    """Individual actionable recommendation."""

    issue: str = Field(..., description="Issue this recommendation addresses")
    tool_id: str | None = Field(None, description="Tool to modify (None if applies to both)")
    recommendation: str = Field(..., description="Specific action to take")
    rationale: str = Field(..., description="Why this recommendation matters")
    priority: str = Field(..., description="Priority: high, medium, low")
    revised_description: str | None = Field(
        None, description="LLM-generated improved tool description (if applicable)"
    )
    apply_commands: list[str] | None = Field(
        None, description="Executable commands or JSON patches to apply changes"
    )


class DifferentiationRecommendation(BaseModel):
    """Actionable recommendation for improving tool differentiation."""

    tool_pair: list[str] = Field(
        ..., min_length=2, max_length=2, description="[tool_a_id, tool_b_id]"
    )
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Overall similarity score")
    issues: list[DifferentiationIssue] = Field(..., description="Identified issues")
    recommendations: list[RecommendationItem] = Field(..., description="Specific recommendations")


class DifferentiationRecommendationResponse(DifferentiationRecommendation):
    """Response schema for recommendations endpoint."""

    generated_at: str = Field(..., description="Generation timestamp (ISO 8601)")


class OverlapMatrixResponse(BaseModel):
    """Response schema for capability overlap matrix."""

    tool_ids: list[str] = Field(..., description="Ordered list of tool IDs")
    matrix: list[list[float]] = Field(..., description="2D overlap matrix")
    dimensions: dict[str, float] = Field(
        ...,
        description="Weights for each dimension (semantic, parameters, description)",
    )
    generated_at: str = Field(..., description="Generation timestamp (ISO 8601)")


class SimilarityAnalysisResponse(SimilarityMatrixResponse):
    """Response schema for full similarity analysis."""

    recommendations: list[DifferentiationRecommendation] | None = Field(
        None, description="Differentiation recommendations (if requested)"
    )
