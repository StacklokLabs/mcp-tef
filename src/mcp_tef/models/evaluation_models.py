"""Internal models for evaluation logic and parameter validation."""

from typing import Any

from pydantic import BaseModel, Field


class ParameterComparison(BaseModel):
    """Model for comparing expected vs actual parameters."""

    parameter_name: str = Field(..., description="Parameter name")
    expected_value: Any = Field(..., description="Expected parameter value")
    actual_value: Any | None = Field(None, description="Actual parameter value from LLM")
    is_present: bool = Field(..., description="Whether parameter is present in LLM response")
    is_correct: bool = Field(
        ..., description="Whether parameter value matches expected (after normalization)"
    )
    type_matches: bool = Field(..., description="Whether parameter type matches schema")
    expected_type: str = Field(..., description="Expected type from schema")
    actual_type: str | None = Field(None, description="Actual type from LLM response")


class ParameterValidationResult(BaseModel):
    """Result of parameter validation analysis."""

    comparisons: list[ParameterComparison] = Field(
        ..., description="Individual parameter comparisons"
    )
    completeness: float = Field(..., ge=0.0, le=1.0, description="Ratio of present required params")
    correctness: float = Field(..., ge=0.0, le=1.0, description="Ratio of correct params")
    type_conformance: bool = Field(..., description="All params match types")
    hallucinated_parameters: list[str] = Field(..., description="Params not in schema")
    missing_required: list[str] = Field(..., description="Required params not present")


class MetricsSummary(BaseModel):
    """Internal model for aggregated metrics calculation."""

    total_tests: int = Field(default=0, ge=0, description="Total evaluated test runs")
    true_positives: int = Field(default=0, ge=0, description="TP count")
    false_positives: int = Field(default=0, ge=0, description="FP count")
    true_negatives: int = Field(default=0, ge=0, description="TN count")
    false_negatives: int = Field(default=0, ge=0, description="FN count")
    precision: float = Field(default=0.0, ge=0.0, le=1.0, description="TP / (TP + FP)")
    recall: float = Field(default=0.0, ge=0.0, le=1.0, description="TP / (TP + FN)")
    f1_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="2 * (Precision * Recall) / (Precision + Recall)"
    )
    parameter_accuracy: float = Field(
        default=0.0, ge=0.0, le=10.0, description="Average parameter correctness (0-10 scale)"
    )
    average_execution_time_ms: float = Field(default=0.0, ge=0.0, description="Average exec time")
    robust_description_count: int = Field(
        default=0, ge=0, description="Count of robust descriptions"
    )
    needs_clarity_count: int = Field(default=0, ge=0, description="Count of needs clarity")
    misleading_description_count: int = Field(
        default=0, ge=0, description="Count of misleading descriptions"
    )
    test_run_ids: list[str] = Field(default_factory=list, description="Test run IDs included")


class ConfidenceAnalysis(BaseModel):
    """Internal model for confidence score analysis."""

    confidence_score: float | None = Field(None, ge=0.0, le=1.0, description="LLM confidence")
    tool_selection_correct: bool = Field(..., description="Whether correct tool was selected")
    confidence_category: str | None = Field(
        None, description="Confidence category (robust/needs_clarity/misleading)"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Recommendations based on confidence pattern"
    )
